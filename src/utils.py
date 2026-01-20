import logging
import os
from datetime import datetime

def setup_logging(log_level=logging.INFO):
    """Setup logging configuration"""
    # Create logs directory
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    # Create log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(log_dir, f"system_{timestamp}.log")
    
    # Configure logging
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()  # Also log to console
        ]
    )
    
    # Create logger
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized. Log file: {log_file}")
    
    return logger

def create_directories():
    """Create necessary project directories"""
    directories = [
        "data/raw",
        "data/processed", 
        "output/signals",
        "logs"
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
    
    print("✅ Project directories created")

def get_system_stats():
    """Get system statistics"""
    import psutil
    
    stats = {
        'cpu_percent': psutil.cpu_percent(interval=1),
        'memory_percent': psutil.virtual_memory().percent,
        'disk_usage': psutil.disk_usage('.').percent,
        'timestamp': datetime.now().isoformat()
    }
    
    return stats

def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    
    return f"{s} {size_names[i]}"

def validate_environment():
    """Validate environment variables and dependencies"""
    required_env_vars = ['TWITTER_EMAIL', 'TWITTER_USERNAME', 'TWITTER_PASSWORD']
    missing_vars = []
    
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        raise ValueError(f"Missing environment variables: {missing_vars}")
    
    # Check if required directories exist
    create_directories()
    
    print("✅ Environment validation passed")

def cleanup_temp_files():
    """Clean up temporary files"""
    import glob
    
    temp_patterns = [
        "*.tmp",
        "*.temp",
        "__pycache__/*",
        "*.pyc"
    ]
    
    removed_count = 0
    for pattern in temp_patterns:
        files = glob.glob(pattern, recursive=True)
        for file in files:
            try:
                os.remove(file)
                removed_count += 1
            except:
                pass
    
    if removed_count > 0:
        print(f"✅ Cleaned up {removed_count} temporary files")

if __name__ == "__main__":
    # Test utilities
    setup_logging()
    validate_environment()
    cleanup_temp_files()
    
    stats = get_system_stats()
    print(f"System Stats: {stats}")