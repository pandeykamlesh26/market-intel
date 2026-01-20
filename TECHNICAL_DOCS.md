# Technical Documentation: Market Intelligence System

## 1. System Architecture

The system follows a modular pipeline architecture designed for reliability, scalability, and maintainability.

### Core Components

1.  **Scraper (`src/scraper.py`)**: Handles data acquisition.
    *   **Technology**: `undetected-chromedriver` + Selenium.
    *   **Design Choice**: Selected over standard Selenium or requests-based scrapers to bypass Twitter's aggressive anti-bot protections.
    *   **Key Features**:
        *   **Human Emulation**: Randomized typing speeds, mouse movements, and pauses using `human_type()` function.
        *   **Session Persistence**: Reuses browser profiles where possible but recreates sessions on failure.
        *   **Contextual Retry**: Distinct retry logic for network errors vs. logical errors (e.g., login flow interruptions).

2.  **Processor (`src/processor.py`)**: Data cleaning and transformation.
    *   **Pipeline**: Raw Text -> Normalization -> Deduplication -> Sentiment Analysis.
    *   **Deduplication**: Uses hashing and text similarity to remove duplicate tweets (e.g., bot spam).
    *   **Sentiment Engine**: TextBlob for polarity (-1 to 1) and subjectivity scoring.

3.  **Storage (`src/storage.py`)**: Efficient data persistence.
    *   **Format**: Apache Parquet.
    *   **Rationale**: Parquet offers superior compression (Snappy) and faster read/write speeds for columnar data compared to CSV/JSON, critical for analyzing thousands of tweets.

4.  **Analyzer (`src/analyzer.py`)**: Signal generation.
    *   **Methodology**: TF-IDF (Term Frequency-Inverse Document Frequency) vectorization.
    *   **Signal Logic**: Converts textual sentiment and engagement metrics (likes, retweets) into a quantitative trading signal (-1 to 1).
    *   **Confidence Scoring**: Calculates statistical confidence based on signal variance.

5.  **Visualizer (`src/visualizer.py`)**: Reporting.
    *   **Library**: Matplotlib + Seaborn.
    *   **Outputs**: Time-series sentiment tracking and signal distribution plots.

## 2. Key Technical Challenges & Solutions

### Rate Limiting & Anti-Bot
*   **Challenge**: Twitter aggressively blocks automated access and imposes strict rate limits.
*   **Solution**:
    *   **Progressive Patience**: The scraper increases its "patience" (number of empty scrolls) as it collects more data, mimicking a user digging deeper.
    *   **Adaptive Delays**: Delays are randomized (e.g., 2.5s - 3.5s) and increase if rate limits approach.
    *   **Session Management**: Logic to detect "Session ID validity" and auto-recover without crashing the pipeline.

### Performance
*   **Challenge**: Processing 3,000+ tweets can be memory-intensive in pure Python.
*   **Solution**:
    *   **Vectorization**: Uses NumPy and Pandas for vectorized operations instead of loops where possible.
    *   **Optimized I/O**: Writes to disk in batches to manage memory usage.

## 3. Data Flow

1.  **Input**: List of hashtags (e.g., `#nifty50`, `#sensex`).
2.  **Collection**: Scraper iterates through tags, collecting data until targets or limits are reached.
3.  **Processing**: Data is cleaned; duplicates removed.
4.  **Analysis**: Sentiment scores computed; TF-IDF vectors generated.
5.  **Output**:
    *   `data/processed/*.parquet`: Structured data.
    *   `output/signals/*.png`: Visual insights.

## 4. Setup & Deployment Implications

*   **Dependencies**: Requires Chrome browser installed. The system auto-patches the driver to match the installed Chrome version.
*   **Environment**: Relies on `.env` for secure credential management, best practice for avoiding hardcoded secrets.
