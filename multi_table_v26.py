"""
Multi-Table Poker Arena v26.0 — pokernow.club
Scales the bulletproof v25.0 system across multiple concurrent tables.

STRATEGY: Use the existing single-table multi_bot.py system and run multiple instances
with proper resource isolation and centralized monitoring.

FEATURES:
- ✅ Isolated browser contexts per table (prevents conflicts)
- ✅ Centralized performance aggregation
- ✅ Graceful failure handling (one table fails, others continue)  
- ✅ Resource-aware scheduling
- ✅ Shared opponent modeling (optional)
- ✅ Live cross-table analytics

USAGE:
    python multi_table_v26.py --tables 2
    python multi_table_v26.py --tables 3 --time-limit 30
"""

import asyncio
import argparse
import sys
import os
import time
import signal
import json
import subprocess
import traceback
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class TableStatus:
    table_id: int
    start_time: float
    hands_played: int = 0
    game_url: Optional[str] = None
    bots: List[str] = None
    process: Optional[subprocess.Popen] = None
    log_file: Optional[str] = None
    last_update: float = 0
    status: str = "STARTING"  # STARTING, RUNNING, COMPLETED, FAILED

class MultiTableManager:
    def __init__(self, num_tables=2, time_limit=None, max_hands=50, log_dir=None):
        self.num_tables = num_tables
        self.time_limit = time_limit  # minutes
        self.max_hands = max_hands
        self.log_dir = log_dir or f"logs/multi_table_{datetime.now().strftime('%Y%m%d_%H%M')}"
        
        # Table tracking
        self.tables: Dict[int, TableStatus] = {}
        self.start_time = time.time()
        self.stop_event = asyncio.Event()
        
        # Create log directory
        os.makedirs(self.log_dir, exist_ok=True)
        
    def log(self, message, table_id=None):
        """Centralized logging with table identification"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = f"T{table_id}" if table_id is not None else "MGR"
        log_msg = f"[{timestamp}] {prefix:>3} {message}"
        print(log_msg)
        
        # Also write to main log file
        with open(f"{self.log_dir}/multi_table_manager.log", "a") as f:
            f.write(log_msg + "\\n")
    
    async def start_table(self, table_id: int) -> bool:
        """Start a single table as a subprocess"""
        try:
            self.log(f"🎯 Starting table {table_id}", table_id)
            
            # Prepare log file for this table
            log_file = f"{self.log_dir}/table_{table_id}.log"
            
            # Environment variables for table-specific configuration
            env = os.environ.copy()
            env['POKER_TABLE_ID'] = str(table_id)
            env['POKER_LOG_PREFIX'] = f"T{table_id}"
            
            # Start the single-table process
            cmd = [
                sys.executable, 
                "multi_bot.py",
                "--profile-offset", str(table_id * 10)  # Different browser profiles per table
            ]
            
            with open(log_file, "w") as f:
                process = subprocess.Popen(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    env=env,
                    cwd=os.getcwd()
                )
            
            # Create table status
            table_status = TableStatus(
                table_id=table_id,
                start_time=time.time(),
                process=process,
                log_file=log_file,
                bots=[f"Clawhi{table_id}", f"AceBot{table_id}", f"NitKing{table_id}", f"CallStn{table_id}"],
                status="STARTING"
            )
            self.tables[table_id] = table_status
            
            self.log(f"✅ Table {table_id} process started (PID: {process.pid})", table_id)
            return True
            
        except Exception as e:
            self.log(f"❌ Failed to start table {table_id}: {str(e)[:100]}", table_id)
            traceback.print_exc()
            return False
    
    async def monitor_table(self, table_id: int):
        """Monitor a single table's progress"""
        table = self.tables[table_id]
        
        while not self.stop_event.is_set():
            try:
                # Check if process is still running
                if table.process.poll() is not None:
                    # Process has finished
                    exit_code = table.process.poll()
                    if exit_code == 0:
                        table.status = "COMPLETED"
                        self.log(f"✅ Table {table_id} completed normally", table_id)
                    else:
                        table.status = "FAILED"
                        self.log(f"❌ Table {table_id} failed (exit code: {exit_code})", table_id)
                    break
                
                # Parse log file for current status
                await self.parse_table_log(table_id)
                
                # Check time limit
                if self.time_limit and (time.time() - table.start_time) > (self.time_limit * 60):
                    self.log(f"⏰ Table {table_id} time limit reached, stopping...", table_id)
                    table.process.terminate()
                    table.status = "COMPLETED"
                    break
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                self.log(f"❌ Monitor error for table {table_id}: {str(e)[:100]}", table_id)
                await asyncio.sleep(5)
    
    async def parse_table_log(self, table_id: int):
        """Parse table log file for current status"""
        table = self.tables[table_id]
        
        try:
            if not os.path.exists(table.log_file):
                return
                
            # Read last few lines to extract current status
            with open(table.log_file, 'r') as f:
                lines = f.readlines()
                
            hands_played = 0
            game_url = None
            
            # Look for key indicators in recent lines
            for line in reversed(lines[-50:]):  # Check last 50 lines
                if "GAME LIVE:" in line:
                    try:
                        game_url = line.split("GAME LIVE:")[1].strip()
                        table.game_url = game_url
                        table.status = "RUNNING"
                    except:
                        pass
                
                # Count hands by looking for decision lines
                if ") | preflop |" in line or ") | flop |" in line or ") | turn |" in line or ") | river |" in line:
                    hands_played += 1
            
            # Update table status
            table.hands_played = max(table.hands_played, hands_played // 4)  # Rough estimate (4 decisions per hand)
            table.last_update = time.time()
            
        except Exception as e:
            # Don't log errors frequently, just update timestamp
            table.last_update = time.time()
    
    async def status_reporter(self):
        """Report aggregated status across all tables"""
        while not self.stop_event.is_set():
            await asyncio.sleep(30)  # Report every 30 seconds
            
            active_tables = sum(1 for t in self.tables.values() if t.status == "RUNNING")
            completed_tables = sum(1 for t in self.tables.values() if t.status == "COMPLETED")
            failed_tables = sum(1 for t in self.tables.values() if t.status == "FAILED")
            total_hands = sum(t.hands_played for t in self.tables.values())
            
            duration = time.time() - self.start_time
            
            self.log(f"📊 MULTI-TABLE STATUS | {active_tables} active, {completed_tables} done, {failed_tables} failed | {total_hands} total hands | {duration/60:.1f}m")
            
            # Individual table summaries
            for table_id, table in self.tables.items():
                age = time.time() - table.start_time
                rate = table.hands_played / max(age/3600, 0.01) if age > 60 else 0
                self.log(f"   T{table_id}: {table.status:<9} | {table.hands_played:>3} hands | {rate:>3.0f}/h | PID:{table.process.pid if table.process else 'N/A'}", table_id)
            
            # Check if all tables are done
            if active_tables == 0 and completed_tables + failed_tables == self.num_tables:
                self.log("🏁 All tables completed")
                self.stop_event.set()
                break
    
    async def cleanup(self):
        """Clean shutdown of all tables"""
        self.log("🧹 Cleaning up tables...")
        
        for table_id, table in self.tables.items():
            if table.process and table.process.poll() is None:
                self.log(f"🛑 Terminating table {table_id} (PID: {table.process.pid})", table_id)
                table.process.terminate()
                
                # Wait up to 10 seconds for graceful shutdown
                try:
                    table.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.log(f"💥 Force killing table {table_id}", table_id)
                    table.process.kill()
    
    async def run_all_tables(self):
        """Main execution - coordinate all tables"""
        try:
            self.log("🚀 Multi-Table Poker Arena v26.0")
            self.log(f"📋 Config: {self.num_tables} tables")
            if self.time_limit:
                self.log(f"⏰ Time limit: {self.time_limit} minutes per table")
            self.log(f"📁 Logs: {self.log_dir}")
            
            # Signal handling
            def signal_handler():
                self.log("🛑 Shutdown signal received...")
                self.stop_event.set()
            
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                try: 
                    loop.add_signal_handler(sig, signal_handler)
                except: 
                    pass
            
            # Start tables with staggered timing
            tasks = []
            for table_id in range(self.num_tables):
                success = await self.start_table(table_id)
                if success:
                    # Start monitoring task
                    monitor_task = asyncio.create_task(self.monitor_table(table_id))
                    tasks.append(monitor_task)
                else:
                    self.log(f"❌ Failed to start table {table_id}, continuing with others", table_id)
                
                # Stagger starts to avoid resource conflicts
                await asyncio.sleep(30)
            
            # Start status reporter
            status_task = asyncio.create_task(self.status_reporter())
            tasks.append(status_task)
            
            # Wait for completion or stop signal
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except Exception as e:
            self.log(f"❌ Multi-table manager error: {e}")
            traceback.print_exc()
        finally:
            await self.cleanup()
            await self.generate_final_report()
    
    async def generate_final_report(self):
        """Generate comprehensive final report"""
        self.log("📊 FINAL MULTI-TABLE REPORT")
        self.log("=" * 60)
        
        total_hands = 0
        total_duration = time.time() - self.start_time
        successful_tables = 0
        
        for table_id, table in self.tables.items():
            duration = time.time() - table.start_time
            rate = table.hands_played / max(duration/3600, 0.01) if duration > 60 else 0
            
            status_emoji = "✅" if table.status == "COMPLETED" else "❌" if table.status == "FAILED" else "⏸️"
            
            self.log(f"   {status_emoji} T{table_id}: {table.hands_played:>3} hands | {rate:>5.0f}/h | {duration/60:>5.1f}m | {table.status}")
            if table.game_url:
                self.log(f"       URL: {table.game_url}")
            
            total_hands += table.hands_played
            if table.status == "COMPLETED":
                successful_tables += 1
        
        overall_rate = total_hands / max(total_duration/3600, 0.01) if total_duration > 60 else 0
        success_rate = successful_tables / self.num_tables * 100 if self.num_tables > 0 else 0
        
        self.log("=" * 60)
        self.log(f"🏆 TOTALS:")
        self.log(f"   📊 {total_hands} hands across {self.num_tables} tables ({overall_rate:.0f} hands/hour)")
        self.log(f"   ⏱️  {total_duration/60:.1f} minutes total duration")
        self.log(f"   ✅ {successful_tables}/{self.num_tables} tables successful ({success_rate:.0f}%)")
        self.log(f"   📁 Logs saved to: {self.log_dir}")
        
        # Save summary to JSON
        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "config": {
                "num_tables": self.num_tables,
                "time_limit": self.time_limit,
                "max_hands": self.max_hands
            },
            "results": {
                "total_hands": total_hands,
                "total_duration_minutes": total_duration / 60,
                "overall_rate_per_hour": overall_rate,
                "successful_tables": successful_tables,
                "success_rate_percent": success_rate
            },
            "tables": {
                str(table_id): {
                    "hands": table.hands_played,
                    "duration_minutes": (time.time() - table.start_time) / 60,
                    "status": table.status,
                    "game_url": table.game_url,
                    "bots": table.bots
                }
                for table_id, table in self.tables.items()
            }
        }
        
        with open(f"{self.log_dir}/summary.json", "w") as f:
            json.dump(summary, f, indent=2)
        
        self.log(f"📄 Summary saved: {self.log_dir}/summary.json")

async def main():
    parser = argparse.ArgumentParser(description='Multi-Table Poker Arena v26.0')
    parser.add_argument('--tables', type=int, default=2, help='Number of concurrent tables (default: 2)')
    parser.add_argument('--time-limit', type=int, help='Time limit in minutes per table (optional)')
    parser.add_argument('--max-hands', type=int, default=50, help='Max hands per table (default: 50)')
    parser.add_argument('--log-dir', type=str, help='Custom log directory')
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.tables < 1 or args.tables > 4:
        print("❌ Error: Tables must be between 1 and 4 (Mac mini resource limit)")
        return
    
    # Estimate resource usage
    estimated_browsers = args.tables * 4  # 4 bots per table
    if estimated_browsers > 16:
        print(f"❌ Error: {estimated_browsers} browsers may exceed Mac mini resources")
        return
    
    print(f"🎯 Starting {args.tables} tables ({estimated_browsers} total browsers)")
    
    manager = MultiTableManager(
        num_tables=args.tables,
        time_limit=args.time_limit,
        max_hands=args.max_hands,
        log_dir=args.log_dir
    )
    
    await manager.run_all_tables()

if __name__ == "__main__":
    asyncio.run(main())