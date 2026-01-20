# Sample Output & Analysis Results

This repository includes real sample data collected and processed by the system.

## 1. Processed Data
**Location**: `data/processed/`

The system stores cleaned and processed tweets in efficient Parquet format.
*   **Format**: Apache Parquet (Snappy compressed)
*   **Schema**:
    *   `id`: Unique Tweet ID
    *   `content`: Cleaned text content
    *   `timestamp`: UTC timestamp
    *   `author`: Username
    *   `metrics`: Like/Retweet/Reply counts
    *   `sentiment_polarity`: Float (-1.0 to 1.0)
    *   `sentiment_subjectivity`: Float (0.0 to 1.0)

## 2. Analysis Visualizations
**Location**: `output/signals/`

The system generates two types of visualizations for every run:

### A. Trading Signals (`signals_*.png`)
Visualizes the generated trading signals over time.
*   **Top Panel**: Signal strength (-1 to +1) for each hashtag.
*   **Middle Panel**: Tweet volume and engagement velocity.
*   **Bottom Panel**: Composite Market Sentiment Score.

### B. Summary Dashboard (`summary_*.png`)
Aggregated view of the market sentiment.
*   **Sentiment Distribution**: Histogram of sentiment scores.
*   **Keyword Cloud**: Top trending terms associated with the hashtags.
*   **Correlation Matrix**: Relationships between different engagement metrics.

## 3. How to View
Since Parquet files are binary:
1.  **Python**:
    ```python
    import pandas as pd
    df = pd.read_parquet('data/processed/tweets_20260120_234204.parquet')
    print(df.head())
    ```
2.  **Visualizations**: Open the `.png` files directly in any image viewer.
