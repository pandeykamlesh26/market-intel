import os
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime
import logging

class DataStorage:
    def __init__(self, base_path="data"):
        self.base_path = base_path
        self.raw_path = os.path.join(base_path, "raw")
        self.processed_path = os.path.join(base_path, "processed")
        self.logger = logging.getLogger(__name__)
        
        # Create directories
        os.makedirs(self.raw_path, exist_ok=True)
        os.makedirs(self.processed_path, exist_ok=True)
    
    def save_tweets(self, tweets, filename=None):
        """Save processed tweets to Parquet format"""
        if not tweets:
            self.logger.warning("No tweets to save")
            return None
        
        try:
            # Convert to DataFrame
            df = pd.DataFrame(tweets)
            
            # Generate filename if not provided
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"tweets_{timestamp}.parquet"
            
            filepath = os.path.join(self.processed_path, filename)
            
            # Save with compression
            df.to_parquet(
                filepath,
                compression='snappy',
                index=False,
                engine='pyarrow'
            )
            
            self.logger.info(f"Saved {len(tweets)} tweets to {filepath}")
            self.logger.info(f"File size: {os.path.getsize(filepath) / 1024 / 1024:.2f} MB")
            
            return filepath
            
        except Exception as e:
            self.logger.error(f"Error saving tweets: {e}")
            return None
    
    def load_tweets(self, filename=None):
        """Load tweets from Parquet file"""
        try:
            if filename:
                filepath = os.path.join(self.processed_path, filename)
            else:
                # Load most recent file
                files = [f for f in os.listdir(self.processed_path) if f.endswith('.parquet')]
                if not files:
                    self.logger.warning("No parquet files found")
                    return pd.DataFrame()
                
                files.sort(reverse=True)
                filepath = os.path.join(self.processed_path, files[0])
            
            df = pd.read_parquet(filepath)
            self.logger.info(f"Loaded {len(df)} tweets from {filepath}")
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error loading tweets: {e}")
            return pd.DataFrame()
    
    def save_raw_data(self, data, filename):
        """Save raw scraped data"""
        try:
            filepath = os.path.join(self.raw_path, filename)
            
            if isinstance(data, list):
                df = pd.DataFrame(data)
                df.to_parquet(filepath, compression='snappy', index=False)
            else:
                # Assume it's already a DataFrame
                data.to_parquet(filepath, compression='snappy', index=False)
            
            self.logger.info(f"Saved raw data to {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"Error saving raw data: {e}")
            return None
    
    def get_storage_stats(self):
        """Get storage statistics"""
        stats = {
            'raw_files': 0,
            'processed_files': 0,
            'total_size_mb': 0
        }
        
        try:
            # Count raw files
            if os.path.exists(self.raw_path):
                raw_files = [f for f in os.listdir(self.raw_path) if f.endswith('.parquet')]
                stats['raw_files'] = len(raw_files)
            
            # Count processed files
            if os.path.exists(self.processed_path):
                processed_files = [f for f in os.listdir(self.processed_path) if f.endswith('.parquet')]
                stats['processed_files'] = len(processed_files)
                
                # Calculate total size
                total_size = 0
                for file in processed_files:
                    filepath = os.path.join(self.processed_path, file)
                    total_size += os.path.getsize(filepath)
                
                stats['total_size_mb'] = total_size / 1024 / 1024
            
        except Exception as e:
            self.logger.error(f"Error getting storage stats: {e}")
        
        return stats
    
    def cleanup_old_files(self, keep_days=7):
        """Clean up old files"""
        try:
            import time
            current_time = time.time()
            cutoff_time = current_time - (keep_days * 24 * 60 * 60)
            
            removed_count = 0
            
            for directory in [self.raw_path, self.processed_path]:
                if not os.path.exists(directory):
                    continue
                
                for filename in os.listdir(directory):
                    if not filename.endswith('.parquet'):
                        continue
                        
                    filepath = os.path.join(directory, filename)
                    
                    if os.path.getmtime(filepath) < cutoff_time:
                        os.remove(filepath)
                        removed_count += 1
            
            self.logger.info(f"Cleaned up {removed_count} old files")
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    def append_tweets(self, new_tweets, main_filename="tweets.parquet"):
        """Append new tweets to existing file"""
        try:
            main_filepath = os.path.join(self.processed_path, main_filename)
            
            # Load existing data if file exists
            if os.path.exists(main_filepath):
                existing_df = pd.read_parquet(main_filepath)
                new_df = pd.DataFrame(new_tweets)
                
                # Combine and deduplicate
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                combined_df = combined_df.drop_duplicates(subset=['id'], keep='last')
                
                self.logger.info(f"Appending {len(new_tweets)} tweets to existing {len(existing_df)} tweets")
            else:
                combined_df = pd.DataFrame(new_tweets)
                self.logger.info(f"Creating new file with {len(new_tweets)} tweets")
            
            # Save combined data
            combined_df.to_parquet(
                main_filepath,
                compression='snappy',
                index=False,
                engine='pyarrow'
            )
            
            self.logger.info(f"Saved {len(combined_df)} total tweets to {main_filepath}")
            return main_filepath
            
        except Exception as e:
            self.logger.error(f"Error appending tweets: {e}")
            return None