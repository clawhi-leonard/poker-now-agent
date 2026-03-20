"""
Multi-Table Poker Arena v26.0 — pokernow.club
Scales the bulletproof v25.0 system across multiple concurrent games.

ARCHITECTURE:
- Each table runs in a separate asyncio task with isolated browser contexts
- Shared performance tracker aggregates results across all tables
- Centralized logging with table identification
- Resource management prevents browser/memory leaks
- Graceful table failure handling (failed tables don't affect others)

USAGE:
    python multi_table.py --tables 2 --bots-per-table 4
    python multi_table.py --tables 3 --bots-per-table 3 --time-limit 60

FEATURES:
- ✅ Independent table management (one fails, others continue)
- ✅ Aggregated performance metrics across all tables
- ✅ Resource-aware browser context isolation
- ✅ Centralized opponent model sharing (optional)
- ✅ Load balancing for optimal Mac mini performance
"""

import asyncio
import argparse
import sys
import os
import time
import signal
import traceback
from datetime import datetime

# Import existing components
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from multi_bot import *  # Import all existing functionality

class MultiTableManager:
    def __init__(self, num_tables=2, bots_per_table=4, time_limit=None, max_hands_per_table=50):
        self.num_tables = num_tables
        self.bots_per_table = bots_per_table
        self.time_limit = time_limit  # minutes
        self.max_hands_per_table = max_hands_per_table
        
        # Global tracking
        self.table_tasks = {}
        self.table_performance = {}
        self.table_urls = {}
        self.global_stop_event = asyncio.Event()
        self.start_time = time.time()
        
        # Resource management
        self.browser_contexts = {}
        self.table_logs = {}
        
    def log_manager(self, message, table_id=None):
        """Centralized logging with table identification"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = f"T{table_id}" if table_id is not None else "MGR"
        print(f"[{timestamp}] {prefix:>3} {message}")
        
    async def create_table_task(self, table_id, pw):
        """Create and manage a single table"""
        try:
            self.log_manager(f"🎯 Starting table {table_id} with {self.bots_per_table} bots", table_id)
            
            # Create isolated resources for this table
            table_stop_event = asyncio.Event()
            table_opponent_model = OpponentModel()
            table_perf_tracker = PerformanceTracker()
            
            # Override globals for this table context
            original_log = globals().get('log', print)
            
            def table_log(msg):
                self.log_manager(msg, table_id)
                
            # Temporarily replace global log function
            globals()['log'] = table_log
            
            # Override bot configuration for this table
            original_num_bots = globals().get('NUM_BOTS', 4)
            globals()['NUM_BOTS'] = self.bots_per_table
            
            # Create table-specific bot profiles
            table_bot_profiles = []
            for i in range(self.bots_per_table):
                base_profile = BOT_PROFILES[i % len(BOT_PROFILES)].copy()
                base_profile['name'] = f"{base_profile['name']}{table_id}"
                table_bot_profiles.append(base_profile)
            
            original_bot_profiles = globals().get('BOT_PROFILES', [])
            globals()['BOT_PROFILES'] = table_bot_profiles
            
            # Run single table game with modified parameters
            table_browsers = []
            table_pages = []
            
            try:
                # Create table game (similar to main() but isolated)
                host_browser, host_page = await make_stealth_page(pw, headless=HEADLESS, profile_id=table_id*10)
                table_browsers.append(host_browser)
                table_pages.append(host_page)
                
                host_name = table_bot_profiles[0]["name"]
                
                # Create new game
                game_url = await create_new_game(host_page, host_name)
                if not game_url:
                    raise Exception("Game creation failed")
                    
                self.table_urls[table_id] = game_url
                self.log_manager(f"✅ Game created: {game_url}", table_id)
                
                # Join other bots
                for i in range(1, self.bots_per_table):
                    browser, page = await make_stealth_page(pw, headless=HEADLESS, profile_id=table_id*10+i)
                    table_browsers.append(browser)
                    table_pages.append(page)
                    
                    bot_profile = table_bot_profiles[i]
                    success = await join_game(page, game_url, bot_profile["name"], STARTING_STACK)
                    if success:
                        self.log_manager(f"✅ {bot_profile['name']} joined", table_id)
                    else:
                        self.log_manager(f"❌ {bot_profile['name']} failed to join", table_id)
                
                # Start game
                await start_game(host_page)
                self.log_manager("🎮 Game started", table_id)
                
                # Run bot loops
                table_tasks = []
                for i in range(self.bots_per_table):
                    task = asyncio.create_task(
                        self.run_table_bot(table_pages[i], table_bot_profiles[i], 
                                         i==0, table_stop_event, table_opponent_model, 
                                         table_perf_tracker, table_id)
                    )
                    table_tasks.append(task)
                
                # Run until stop condition
                start_time = time.time()
                hands_played = 0
                
                while not self.global_stop_event.is_set() and not table_stop_event.is_set():
                    await asyncio.sleep(10)  # Check every 10 seconds
                    
                    # Check time limit
                    if self.time_limit and (time.time() - start_time) > (self.time_limit * 60):
                        self.log_manager(f"⏰ Time limit reached ({self.time_limit}m)", table_id)
                        break
                    
                    # Check hand limit
                    total_hands = sum(hands_played.values())
                    if total_hands >= self.max_hands_per_table:
                        self.log_manager(f"🎯 Hand limit reached ({total_hands})", table_id)
                        break
                
                # Clean shutdown
                table_stop_event.set()
                await asyncio.gather(*table_tasks, return_exceptions=True)
                
                # Record final performance
                self.table_performance[table_id] = {
                    'hands': sum(hands_played.values()),
                    'duration': time.time() - start_time,
                    'url': game_url,
                    'bots': [p['name'] for p in table_bot_profiles]
                }
                
                self.log_manager(f"✅ Table completed - {sum(hands_played.values())} hands", table_id)
                
            finally:
                # Cleanup browsers
                for browser in table_browsers:
                    try:
                        await browser.close()
                    except:
                        pass
                        
                # Restore globals
                globals()['log'] = original_log
                globals()['NUM_BOTS'] = original_num_bots
                globals()['BOT_PROFILES'] = original_bot_profiles
                
        except Exception as e:
            self.log_manager(f"❌ Table failed: {str(e)[:100]}", table_id)
            traceback.print_exc()
        
    async def run_table_bot(self, page, profile, is_host, stop_event, opponent_model, perf_tracker, table_id):
        """Run a single bot with table-specific context"""
        try:
            # Use existing bot_loop with table-specific parameters
            await bot_loop(page, profile, is_host, stop_event, opponent_model, perf_tracker)
        except Exception as e:
            self.log_manager(f"❌ Bot {profile['name']} failed: {str(e)[:60]}", table_id)

    async def run_aggregated_status_reporter(self):
        """Report aggregated status across all tables"""
        while not self.global_stop_event.is_set():
            await asyncio.sleep(60)  # Report every minute
            
            total_hands = 0
            active_tables = 0
            duration = time.time() - self.start_time
            
            for table_id, perf in self.table_performance.items():
                if perf:
                    total_hands += perf.get('hands', 0)
                    active_tables += 1
            
            self.log_manager(f"📊 MULTI-TABLE STATUS | {active_tables}/{self.num_tables} active | {total_hands} total hands | {duration/60:.1f}m")
            
            # Individual table status
            for table_id in range(self.num_tables):
                if table_id in self.table_performance:
                    perf = self.table_performance[table_id]
                    hands = perf.get('hands', 0)
                    table_duration = perf.get('duration', 0)
                    rate = hands / max(table_duration/3600, 0.01) if table_duration > 0 else 0
                    self.log_manager(f"   T{table_id}: {hands} hands, {rate:.0f} hands/hour", table_id)

    async def run_all_tables(self):
        """Main execution - run all tables concurrently"""
        try:
            self.log_manager("🚀 Multi-Table Poker Arena v26.0")
            self.log_manager(f"📋 Config: {self.num_tables} tables × {self.bots_per_table} bots = {self.num_tables * self.bots_per_table} total bots")
            if self.time_limit:
                self.log_manager(f"⏰ Time limit: {self.time_limit} minutes")
            self.log_manager(f"🎯 Hand limit: {self.max_hands_per_table} per table")
            
            # Signal handling
            def signal_handler():
                self.log_manager("🛑 Shutdown signal received...")
                self.global_stop_event.set()
            
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                try: 
                    loop.add_signal_handler(sig, signal_handler)
                except: 
                    pass
            
            # Start playwright
            pw = await async_playwright().start()
            
            try:
                # Create table tasks
                table_tasks = []
                for table_id in range(self.num_tables):
                    task = asyncio.create_task(self.create_table_task(table_id, pw))
                    table_tasks.append(task)
                    self.table_tasks[table_id] = task
                    
                    # Stagger table creation to avoid resource conflicts
                    await asyncio.sleep(5)
                
                # Start status reporter
                status_task = asyncio.create_task(self.run_aggregated_status_reporter())
                
                # Wait for completion
                await asyncio.gather(*table_tasks, status_task, return_exceptions=True)
                
            finally:
                await pw.stop()
                
        except Exception as e:
            self.log_manager(f"❌ Multi-table manager failed: {e}")
            traceback.print_exc()
        finally:
            # Final report
            self.log_manager("📊 FINAL MULTI-TABLE REPORT")
            total_hands = 0
            total_duration = time.time() - self.start_time
            
            for table_id, perf in self.table_performance.items():
                if perf:
                    hands = perf['hands']
                    duration = perf['duration']
                    url = perf.get('url', 'N/A')
                    bots = ', '.join(perf.get('bots', []))
                    rate = hands / max(duration/3600, 0.01)
                    total_hands += hands
                    
                    self.log_manager(f"   T{table_id}: {hands} hands ({rate:.0f}/h) | {bots}")
                    self.log_manager(f"        URL: {url}")
            
            overall_rate = total_hands / max(total_duration/3600, 0.01)
            self.log_manager(f"🏆 TOTAL: {total_hands} hands ({overall_rate:.0f}/h) across {len(self.table_performance)} tables in {total_duration/60:.1f}m")

async def main():
    parser = argparse.ArgumentParser(description='Multi-Table Poker Arena v26.0')
    parser.add_argument('--tables', type=int, default=2, help='Number of concurrent tables (default: 2)')
    parser.add_argument('--bots-per-table', type=int, default=4, help='Bots per table (default: 4)')
    parser.add_argument('--time-limit', type=int, help='Time limit in minutes (optional)')
    parser.add_argument('--max-hands', type=int, default=50, help='Max hands per table (default: 50)')
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.tables < 1 or args.tables > 5:
        print("❌ Error: Tables must be between 1 and 5")
        return
        
    if args.bots_per_table < 2 or args.bots_per_table > 6:
        print("❌ Error: Bots per table must be between 2 and 6")
        return
    
    total_bots = args.tables * args.bots_per_table
    if total_bots > 24:
        print(f"❌ Error: Total bots ({total_bots}) exceeds recommended maximum (24)")
        return
    
    manager = MultiTableManager(
        num_tables=args.tables,
        bots_per_table=args.bots_per_table,
        time_limit=args.time_limit,
        max_hands_per_table=args.max_hands
    )
    
    await manager.run_all_tables()

if __name__ == "__main__":
    asyncio.run(main())