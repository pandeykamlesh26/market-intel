import re
import pandas as pd
import numpy as np
from datetime import datetime
import logging
from textblob import TextBlob
import unicodedata

class DataProcessor:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def clean_text(self, text):
        """Clean and normalize tweet text"""
        if not text:
            return ""
        
        # Normalize Unicode characters
        text = unicodedata.normalize('NFKD', text)
        
        # Remove URLs
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Handle Indian language content (keep as is for sentiment analysis)
        return text
    
    def extract_metrics(self, metric_text):
        """Extract numeric values from engagement metrics"""
        if not metric_text or metric_text == "0":
            return 0
        
        # Handle K, M suffixes
        metric_text = str(metric_text).lower().replace(',', '')
        
        if 'k' in metric_text:
            return int(float(metric_text.replace('k', '')) * 1000)
        elif 'm' in metric_text:
            return int(float(metric_text.replace('m', '')) * 1000000)
        else:
            try:
                return int(metric_text)
            except (ValueError, TypeError):
                return 0
    
    def calculate_sentiment(self, text):
        """Calculate sentiment polarity and subjectivity"""
        try:
            blob = TextBlob(text)
            return {
                'polarity': blob.sentiment.polarity,
                'subjectivity': blob.sentiment.subjectivity
            }
        except Exception:
            return {'polarity': 0.0, 'subjectivity': 0.0}
    
    def deduplicate_tweets(self, tweets):
        """Remove duplicate tweets based on text similarity"""
        seen_texts = set()
        unique_tweets = []
        
        for tweet in tweets:
            # Create a normalized version for comparison
            normalized_text = re.sub(r'[^\w\s]', '', tweet['text'].lower())
            
            if normalized_text not in seen_texts:
                seen_texts.add(normalized_text)
                unique_tweets.append(tweet)
        
        self.logger.info(f"Removed {len(tweets) - len(unique_tweets)} duplicate tweets")
        return unique_tweets
    
    def process_tweets(self, raw_tweets):
        """Process and clean tweet data"""
        if not raw_tweets:
            return []
        
        self.logger.info(f"Processing {len(raw_tweets)} raw tweets...")
        
        # Deduplicate first
        tweets = self.deduplicate_tweets(raw_tweets)
        
        processed_tweets = []
        
        for tweet in tweets:
            try:
                # Clean text
                cleaned_text = self.clean_text(tweet.get('text', ''))
                
                if not cleaned_text or len(cleaned_text) < 10:
                    continue
                
                # Extract engagement metrics
                replies = self.extract_metrics(tweet.get('replies', 0))
                retweets = self.extract_metrics(tweet.get('retweets', 0))
                likes = self.extract_metrics(tweet.get('likes', 0))
                
                # Calculate engagement score
                engagement_score = replies + (retweets * 2) + likes
                
                # Calculate sentiment
                sentiment = self.calculate_sentiment(cleaned_text)
                
                # Process hashtags and mentions
                hashtags = [tag.lower() for tag in tweet.get('hashtags', [])]
                mentions = tweet.get('mentions', [])
                
                # Create processed tweet
                processed_tweet = {
                    'id': hash(cleaned_text) % (10**8),  # Simple ID generation
                    'username': tweet.get('username', 'unknown'),
                    'text': cleaned_text,
                    'text_length': len(cleaned_text),
                    'word_count': len(cleaned_text.split()),
                    'hashtag': tweet.get('hashtag', ''),
                    'hashtags': hashtags,
                    'hashtag_count': len(hashtags),
                    'mentions': mentions,
                    'mention_count': len(mentions),
                    'replies': replies,
                    'retweets': retweets,
                    'likes': likes,
                    'engagement_score': engagement_score,
                    'sentiment_polarity': sentiment['polarity'],
                    'sentiment_subjectivity': sentiment['subjectivity'],
                    'timestamp': tweet.get('timestamp', datetime.now().isoformat()),
                    'scraped_at': tweet.get('scraped_at', datetime.now().timestamp()),
                    'processed_at': datetime.now().timestamp()
                }
                
                processed_tweets.append(processed_tweet)
                
            except Exception as e:
                self.logger.warning(f"Error processing tweet: {e}")
                continue
        
        self.logger.info(f"Successfully processed {len(processed_tweets)} tweets")
        return processed_tweets
    
    def get_processing_stats(self, processed_tweets):
        """Get processing statistics"""
        if not processed_tweets:
            return {}
        
        df = pd.DataFrame(processed_tweets)
        
        stats = {
            'total_tweets': len(processed_tweets),
            'unique_users': df['username'].nunique(),
            'avg_engagement': df['engagement_score'].mean(),
            'avg_sentiment': df['sentiment_polarity'].mean(),
            'hashtag_distribution': df['hashtag'].value_counts().to_dict(),
            'sentiment_distribution': {
                'positive': len(df[df['sentiment_polarity'] > 0.1]),
                'neutral': len(df[df['sentiment_polarity'].between(-0.1, 0.1)]),
                'negative': len(df[df['sentiment_polarity'] < -0.1])
            }
        }
        
        return stats