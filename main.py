#!/usr/bin/env python3
"""
Market Intelligence System - Main Pipeline
Real-time Twitter data collection and analysis for Indian stock market
"""

import os
import logging
from dotenv import load_dotenv
from src.scraper import TwitterScraper
from src.processor import DataProcessor
from src.storage import DataStorage
from src.analyzer import SignalAnalyzer
from src.visualizer import DataVisualizer
from src.utils import setup_logging

def main():
    """Main pipeline execution"""
    # Load environment variables
    load_dotenv()
    
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("[START] Market Intelligence System")
    
    # Configuration - Expanded hashtag list for better coverage
    hashtags = [
        'nifty50', 'sensex', 'banknifty', 'intraday',  # Original 4
        'stockmarket', 'nse', 'bse', 'trading', 'stocks'  # Added 5 more
    ]
    tweets_per_hashtag = 750  # Target 3000+ total tweets (now with 9 hashtags = 6750 potential)
    
    try:
        # 1. Data Collection
        logger.info("[PHASE] Data Collection starting")
        scraper = TwitterScraper()
        raw_tweets = scraper.scrape_multiple_hashtags(hashtags, tweets_per_hashtag)
        
        if not raw_tweets:
            logger.error("[ERROR] No tweets collected. Exiting.")
            return
        
        logger.info(f"[SUCCESS] Collected {len(raw_tweets)} tweets")
        
        # 2. Data Processing
        logger.info("[PHASE] Data Processing starting")
        processor = DataProcessor()
        processed_tweets = processor.process_tweets(raw_tweets)
        logger.info(f"[SUCCESS] Processed {len(processed_tweets)} tweets")
        
        # 3. Data Storage
        logger.info("[PHASE] Data Storage starting")
        storage = DataStorage()
        storage.save_tweets(processed_tweets)
        logger.info("[SUCCESS] Data saved to Parquet format")
        
        # 4. Signal Analysis
        logger.info("[PHASE] Signal Analysis starting")
        analyzer = SignalAnalyzer()
        signals = analyzer.generate_signals(processed_tweets)
        logger.info(f"[SUCCESS] Generated {len(signals)} trading signals")
        
        # 5. Visualization
        logger.info("[PHASE] Visualization starting")
        visualizer = DataVisualizer()
        visualizer.create_signal_plots(signals, processed_tweets)
        logger.info("[SUCCESS] Visualizations created")
        
        # Summary
        logger.info("[COMPLETE] Pipeline completed successfully!")
        logger.info(f"[SUMMARY] Statistics:")
        logger.info(f"   - Tweets collected: {len(raw_tweets)}")
        logger.info(f"   - Tweets processed: {len(processed_tweets)}")
        logger.info(f"   - Trading signals: {len(signals)}")
        logger.info(f"   - Output files: data/processed/tweets.parquet, output/signals/plot.png")
        
    except Exception as e:
        logger.error(f"[ERROR] Pipeline failed: {e}")
        raise
    
    finally:
        logger.info("[END] Pipeline execution completed")

if __name__ == "__main__":
    main()