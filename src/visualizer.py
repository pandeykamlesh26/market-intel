import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
import os
from datetime import datetime
import logging

class DataVisualizer:
    def __init__(self, output_dir="output/signals"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        
        # Set style for better plots
        plt.style.use('seaborn-v0_8')
        sns.set_palette("husl")
    
    def create_signal_plots(self, signals, tweets, max_points=1000):
        """Create comprehensive signal visualization"""
        try:
            if not signals:
                self.logger.warning("No signals to visualize")
                return
            
            # Sample data if too large for memory efficiency
            if len(signals) > max_points:
                sample_indices = np.random.choice(len(signals), max_points, replace=False)
                signals_sample = [signals[i] for i in sample_indices]
                tweets_sample = [tweets[i] for i in sample_indices]
                self.logger.info(f"Sampling {max_points} points from {len(signals)} for visualization")
            else:
                signals_sample = signals
                tweets_sample = tweets
            
            # Create figure with subplots
            fig, axes = plt.subplots(2, 2, figsize=(15, 12))
            fig.suptitle('Market Intelligence Trading Signals', fontsize=16, fontweight='bold')
            
            # Convert to DataFrame for easier plotting
            df_signals = pd.DataFrame(signals_sample)
            df_tweets = pd.DataFrame(tweets_sample)
            
            # Plot 1: Signal Distribution by Hashtag
            ax1 = axes[0, 0]
            signal_by_hashtag = df_signals.groupby('hashtag')['signal_value'].mean().sort_values()
            signal_by_hashtag.plot(kind='barh', ax=ax1, color='skyblue')
            ax1.set_title('Average Signal Strength by Hashtag')
            ax1.set_xlabel('Signal Value')
            ax1.axvline(x=0, color='red', linestyle='--', alpha=0.7)
            
            # Plot 2: Signal vs Sentiment Scatter
            ax2 = axes[0, 1]
            scatter = ax2.scatter(df_signals['sentiment_component'], 
                                df_signals['signal_value'],
                                c=df_signals['confidence'],
                                cmap='viridis',
                                alpha=0.6,
                                s=30)
            ax2.set_xlabel('Sentiment Component')
            ax2.set_ylabel('Signal Value')
            ax2.set_title('Signal vs Sentiment (Color = Confidence)')
            plt.colorbar(scatter, ax=ax2, label='Confidence')
            ax2.axhline(y=0, color='red', linestyle='--', alpha=0.7)
            ax2.axvline(x=0, color='red', linestyle='--', alpha=0.7)
            
            # Plot 3: Signal Direction Distribution
            ax3 = axes[1, 0]
            direction_counts = df_signals['signal_direction'].value_counts()
            colors = ['green' if x == 'bullish' else 'red' if x == 'bearish' else 'gray' 
                     for x in direction_counts.index]
            direction_counts.plot(kind='pie', ax=ax3, colors=colors, autopct='%1.1f%%')
            ax3.set_title('Signal Direction Distribution')
            ax3.set_ylabel('')
            
            # Plot 4: Engagement vs Signal Strength
            ax4 = axes[1, 1]
            # Create engagement bins for better visualization
            df_combined = pd.concat([df_signals, df_tweets[['engagement_score']]], axis=1)
            df_combined['engagement_bin'] = pd.cut(df_combined['engagement_score'], 
                                                 bins=5, labels=['Very Low', 'Low', 'Medium', 'High', 'Very High'])
            
            engagement_signal = df_combined.groupby('engagement_bin')['signal_value'].agg(['mean', 'std']).fillna(0)
            engagement_signal['mean'].plot(kind='bar', ax=ax4, yerr=engagement_signal['std'], 
                                         capsize=4, color='orange', alpha=0.7)
            ax4.set_title('Signal Strength by Engagement Level')
            ax4.set_xlabel('Engagement Level')
            ax4.set_ylabel('Average Signal Value')
            ax4.tick_params(axis='x', rotation=45)
            ax4.axhline(y=0, color='red', linestyle='--', alpha=0.7)
            
            plt.tight_layout()
            
            # Save plot
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            plot_path = os.path.join(self.output_dir, f"signals_{timestamp}.png")
            plt.savefig(plot_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            self.logger.info(f"Signal plots saved to {plot_path}")
            
            # Create summary statistics plot
            self._create_summary_stats_plot(signals_sample, tweets_sample)
            
        except Exception as e:
            self.logger.error(f"Error creating signal plots: {e}")
    
    def _create_summary_stats_plot(self, signals, tweets):
        """Create summary statistics visualization"""
        try:
            fig, axes = plt.subplots(1, 3, figsize=(18, 6))
            fig.suptitle('Market Intelligence Summary Statistics', fontsize=16, fontweight='bold')
            
            df_signals = pd.DataFrame(signals)
            df_tweets = pd.DataFrame(tweets)
            
            # Plot 1: Signal Value Distribution
            ax1 = axes[0]
            ax1.hist(df_signals['signal_value'], bins=30, alpha=0.7, color='blue', edgecolor='black')
            ax1.axvline(df_signals['signal_value'].mean(), color='red', linestyle='--', 
                       label=f'Mean: {df_signals["signal_value"].mean():.3f}')
            ax1.set_xlabel('Signal Value')
            ax1.set_ylabel('Frequency')
            ax1.set_title('Signal Value Distribution')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # Plot 2: Confidence Distribution
            ax2 = axes[1]
            ax2.hist(df_signals['confidence'], bins=20, alpha=0.7, color='green', edgecolor='black')
            ax2.axvline(df_signals['confidence'].mean(), color='red', linestyle='--',
                       label=f'Mean: {df_signals["confidence"].mean():.3f}')
            ax2.set_xlabel('Confidence')
            ax2.set_ylabel('Frequency')
            ax2.set_title('Signal Confidence Distribution')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            
            # Plot 3: Sentiment vs Engagement Heatmap
            ax3 = axes[2]
            
            # Create bins for heatmap
            sentiment_bins = pd.cut(df_tweets['sentiment_polarity'], bins=5)
            engagement_bins = pd.cut(df_tweets['engagement_score'], bins=5)
            
            heatmap_data = pd.crosstab(sentiment_bins, engagement_bins, 
                                     values=df_signals['signal_value'], aggfunc='mean')
            
            sns.heatmap(heatmap_data, annot=True, fmt='.3f', cmap='RdYlBu_r', 
                       center=0, ax=ax3, cbar_kws={'label': 'Average Signal'})
            ax3.set_title('Signal Heatmap: Sentiment vs Engagement')
            ax3.set_xlabel('Engagement Level')
            ax3.set_ylabel('Sentiment Level')
            
            plt.tight_layout()
            
            # Save summary plot
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            summary_path = os.path.join(self.output_dir, f"summary_{timestamp}.png")
            plt.savefig(summary_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            self.logger.info(f"Summary plots saved to {summary_path}")
            
        except Exception as e:
            self.logger.error(f"Error creating summary plots: {e}")
    
    def create_streaming_plot(self, signals, window_size=100):
        """Create memory-efficient streaming plot for large datasets"""
        try:
            if len(signals) <= window_size:
                return self.create_signal_plots(signals, [])
            
            # Process in chunks
            num_chunks = len(signals) // window_size + 1
            
            fig, ax = plt.subplots(figsize=(12, 6))
            
            for i in range(num_chunks):
                start_idx = i * window_size
                end_idx = min((i + 1) * window_size, len(signals))
                
                chunk_signals = signals[start_idx:end_idx]
                signal_values = [s['signal_value'] for s in chunk_signals]
                
                x_values = range(start_idx, end_idx)
                ax.plot(x_values, signal_values, alpha=0.7, linewidth=1)
            
            ax.set_xlabel('Tweet Index')
            ax.set_ylabel('Signal Value')
            ax.set_title(f'Streaming Signal Plot ({len(signals)} total signals)')
            ax.axhline(y=0, color='red', linestyle='--', alpha=0.7)
            ax.grid(True, alpha=0.3)
            
            # Save streaming plot
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            streaming_path = os.path.join(self.output_dir, f"streaming_{timestamp}.png")
            plt.savefig(streaming_path, dpi=150, bbox_inches='tight')
            plt.close()
            
            self.logger.info(f"Streaming plot saved to {streaming_path}")
            
        except Exception as e:
            self.logger.error(f"Error creating streaming plot: {e}")
    
    def generate_signal_report(self, signals, tweets):
        """Generate text report of signal analysis"""
        try:
            if not signals:
                return
            
            df_signals = pd.DataFrame(signals)
            df_tweets = pd.DataFrame(tweets)
            
            report_lines = [
                "="*60,
                "MARKET INTELLIGENCE SIGNAL REPORT",
                "="*60,
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"Total Signals: {len(signals)}",
                "",
                "SIGNAL STATISTICS:",
                f"  Mean Signal Value: {df_signals['signal_value'].mean():.4f}",
                f"  Signal Std Dev: {df_signals['signal_value'].std():.4f}",
                f"  Signal Range: [{df_signals['signal_value'].min():.4f}, {df_signals['signal_value'].max():.4f}]",
                f"  Average Confidence: {df_signals['confidence'].mean():.4f}",
                "",
                "SIGNAL DIRECTIONS:",
            ]
            
            direction_counts = df_signals['signal_direction'].value_counts()
            for direction, count in direction_counts.items():
                percentage = (count / len(signals)) * 100
                report_lines.append(f"  {direction.capitalize()}: {count} ({percentage:.1f}%)")
            
            report_lines.extend([
                "",
                "HASHTAG ANALYSIS:",
            ])
            
            hashtag_signals = df_signals.groupby('hashtag')['signal_value'].agg(['mean', 'count'])
            for hashtag, stats in hashtag_signals.iterrows():
                report_lines.append(f"  #{hashtag}: Avg Signal = {stats['mean']:.4f}, Count = {stats['count']}")
            
            report_lines.extend([
                "",
                "TOP STRONG SIGNALS:",
            ])
            
            strong_signals = df_signals[df_signals['signal_strength'] == 'strong'].nlargest(5, 'confidence')
            for _, signal in strong_signals.iterrows():
                report_lines.append(f"  {signal['signal_direction'].upper()}: {signal['signal_value']:.4f} (confidence: {signal['confidence']:.3f})")
            
            report_lines.append("="*60)
            
            # Save report
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = os.path.join(self.output_dir, f"report_{timestamp}.txt")
            
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(report_lines))
            
            self.logger.info(f"Signal report saved to {report_path}")
            
        except Exception as e:
            self.logger.error(f"Error generating signal report: {e}")