import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import StandardScaler
import logging
from datetime import datetime

class SignalAnalyzer:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.vectorizer = None
        self.scaler = StandardScaler()
        
    def preprocess_text_for_tfidf(self, texts):
        """Preprocess texts for TF-IDF"""
        processed_texts = []
        
        for text in texts:
            if not text:
                processed_texts.append("")
                continue
            
            # Convert to lowercase and basic cleaning
            text = str(text).lower()
            
            # Remove special characters but keep important market terms
            import re
            text = re.sub(r'[^\w\s#@]', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            
            processed_texts.append(text)
        
        return processed_texts
    
    def extract_tfidf_features(self, tweets):
        """Extract TF-IDF features from tweet texts"""
        try:
            texts = [tweet['text'] for tweet in tweets]
            processed_texts = self.preprocess_text_for_tfidf(texts)
            
            # TF-IDF with market-specific parameters
            self.vectorizer = TfidfVectorizer(
                max_features=1000,
                ngram_range=(1, 2),
                min_df=2,
                max_df=0.8,
                stop_words='english'
            )
            
            tfidf_matrix = self.vectorizer.fit_transform(processed_texts)
            
            # Dimensionality reduction for efficiency
            svd = TruncatedSVD(n_components=50, random_state=42)
            tfidf_reduced = svd.fit_transform(tfidf_matrix)
            
            self.logger.info(f"Extracted TF-IDF features: {tfidf_reduced.shape}")
            
            return tfidf_reduced, svd.explained_variance_ratio_
            
        except Exception as e:
            self.logger.error(f"Error extracting TF-IDF features: {e}")
            return np.array([]), np.array([])
    
    def calculate_market_sentiment_score(self, tweets):
        """Calculate market sentiment scores"""
        sentiment_scores = []
        
        for tweet in tweets:
            # Base sentiment from TextBlob
            base_sentiment = tweet.get('sentiment_polarity', 0)
            
            # Engagement weight (higher engagement = more influence)
            engagement = tweet.get('engagement_score', 0)
            engagement_weight = min(np.log1p(engagement) / 10, 1.0)  # Normalize to 0-1
            
            # Hashtag relevance weight
            hashtag_weight = 1.0
            relevant_hashtags = ['nifty50', 'sensex', 'banknifty', 'intraday']
            tweet_hashtags = [h.lower() for h in tweet.get('hashtags', [])]
            
            if any(h in tweet_hashtags for h in relevant_hashtags):
                hashtag_weight = 1.5
            
            # Calculate weighted sentiment
            weighted_sentiment = base_sentiment * (1 + engagement_weight) * hashtag_weight
            sentiment_scores.append(weighted_sentiment)
        
        return np.array(sentiment_scores)
    
    def generate_trading_signals(self, tfidf_features, sentiment_scores, tweets):
        """Generate trading signals from features"""
        try:
            if len(tfidf_features) == 0:
                return []
            
            # Combine TF-IDF features with sentiment and engagement
            engagement_scores = np.array([tweet.get('engagement_score', 0) for tweet in tweets])
            
            # Normalize engagement scores
            engagement_normalized = np.log1p(engagement_scores)
            engagement_normalized = (engagement_normalized - engagement_normalized.mean()) / (engagement_normalized.std() + 1e-8)
            
            # Create feature matrix
            features = np.column_stack([
                tfidf_features,
                sentiment_scores.reshape(-1, 1),
                engagement_normalized.reshape(-1, 1)
            ])
            
            # Scale features
            features_scaled = self.scaler.fit_transform(features)
            
            # Generate signals using weighted combination
            signal_weights = np.array([0.6, 0.3, 0.1])  # TF-IDF, sentiment, engagement
            
            # Calculate composite signals
            tfidf_signal = np.mean(features_scaled[:, :-2], axis=1)  # Average TF-IDF components
            sentiment_signal = features_scaled[:, -2]
            engagement_signal = features_scaled[:, -1]
            
            composite_signals = (
                tfidf_signal * signal_weights[0] +
                sentiment_signal * signal_weights[1] +
                engagement_signal * signal_weights[2]
            )
            
            # Calculate confidence intervals
            signal_std = np.std(composite_signals)
            confidence_intervals = np.abs(composite_signals) / (signal_std + 1e-8)
            
            # Normalize signals to [-1, 1] range
            signals_normalized = np.tanh(composite_signals)
            
            # Create signal objects
            signals = []
            for i, (signal, confidence) in enumerate(zip(signals_normalized, confidence_intervals)):
                signal_obj = {
                    'tweet_id': tweets[i].get('id', i),
                    'hashtag': tweets[i].get('hashtag', ''),
                    'signal_value': float(signal),
                    'confidence': float(min(confidence, 1.0)),
                    'signal_strength': 'strong' if abs(signal) > 0.5 else 'weak',
                    'signal_direction': 'bullish' if signal > 0.1 else 'bearish' if signal < -0.1 else 'neutral',
                    'sentiment_component': float(sentiment_signal[i]),
                    'engagement_component': float(engagement_signal[i]),
                    'tfidf_component': float(tfidf_signal[i]),
                    'timestamp': tweets[i].get('timestamp', datetime.now().isoformat())
                }
                signals.append(signal_obj)
            
            self.logger.info(f"Generated {len(signals)} trading signals")
            return signals
            
        except Exception as e:
            self.logger.error(f"Error generating trading signals: {e}")
            return []
    
    def aggregate_signals_by_hashtag(self, signals):
        """Aggregate signals by hashtag"""
        try:
            df = pd.DataFrame(signals)
            
            if df.empty:
                return {}
            
            aggregated = df.groupby('hashtag').agg({
                'signal_value': ['mean', 'std', 'count'],
                'confidence': 'mean',
                'sentiment_component': 'mean',
                'engagement_component': 'mean'
            }).round(4)
            
            # Flatten column names
            aggregated.columns = ['_'.join(col).strip() for col in aggregated.columns]
            
            # Calculate overall signal strength
            aggregated['overall_signal'] = aggregated['signal_value_mean']
            aggregated['signal_reliability'] = aggregated['confidence_mean'] * np.sqrt(aggregated['signal_value_count'])
            
            return aggregated.to_dict('index')
            
        except Exception as e:
            self.logger.error(f"Error aggregating signals: {e}")
            return {}
    
    def generate_signals(self, tweets):
        """Main signal generation pipeline"""
        try:
            if not tweets:
                self.logger.warning("No tweets provided for signal generation")
                return []
            
            self.logger.info(f"Generating signals for {len(tweets)} tweets")
            
            # Extract TF-IDF features
            tfidf_features, variance_ratio = self.extract_tfidf_features(tweets)
            
            if len(tfidf_features) == 0:
                self.logger.warning("No TF-IDF features extracted")
                return []
            
            # Calculate sentiment scores
            sentiment_scores = self.calculate_market_sentiment_score(tweets)
            
            # Generate trading signals
            signals = self.generate_trading_signals(tfidf_features, sentiment_scores, tweets)
            
            # Log signal statistics
            if signals:
                signal_values = [s['signal_value'] for s in signals]
                self.logger.info(f"Signal statistics:")
                self.logger.info(f"  Mean: {np.mean(signal_values):.4f}")
                self.logger.info(f"  Std: {np.std(signal_values):.4f}")
                self.logger.info(f"  Range: [{np.min(signal_values):.4f}, {np.max(signal_values):.4f}]")
                
                # Count signal directions
                directions = [s['signal_direction'] for s in signals]
                direction_counts = pd.Series(directions).value_counts()
                self.logger.info(f"  Directions: {direction_counts.to_dict()}")
            
            return signals
            
        except Exception as e:
            self.logger.error(f"Error in signal generation pipeline: {e}")
            return []