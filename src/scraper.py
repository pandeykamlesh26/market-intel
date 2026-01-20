import os
import time
import random
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from datetime import datetime, timedelta
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Optional

class RateLimitException(Exception):
    """Custom exception for rate limit errors"""
    def __init__(self, message: str, reset_after: Optional[float] = None):
        self.message = message
        self.reset_after = reset_after  # Time to wait before retry (seconds)
        super().__init__(self.message)

class RateLimitStatus(Enum):
    """Rate limit status enumeration"""
    OK = "ok"
    APPROACHING = "approaching"  # 75% limit reached
    LIMITED = "limited"  # 429 or explicit rate limit hit
    COOLDOWN = "cooldown"  # In retry backoff

@dataclass
class EndpointRateLimit:
    """Track rate limit for specific endpoint"""
    endpoint: str
    requests_made: int = 0
    requests_limit: int = 100
    reset_time: float = field(default_factory=time.time)
    last_request_time: float = 0
    backoff_count: int = 0
    max_backoff_count: int = 5
    
    def is_rate_limited(self) -> bool:
        """Check if endpoint is rate limited"""
        return self.requests_made >= self.requests_limit
    
    def can_request(self) -> bool:
        """Check if request can be made"""
        current_time = time.time()
        if current_time >= self.reset_time:
            # Reset window expired
            self.requests_made = 0
            self.reset_time = current_time + 900  # 15 minute window
            self.backoff_count = 0
            return True
        return not self.is_rate_limited()
    
    def record_request(self):
        """Record a request"""
        self.requests_made += 1
        self.last_request_time = time.time()
    
    def get_reset_in_seconds(self) -> float:
        """Get seconds until rate limit resets"""
        return max(0, self.reset_time - time.time())

class TwitterScraper:
    def __init__(self):
        self.driver = None
        self.email = os.getenv('TWITTER_EMAIL')
        self.username = os.getenv('TWITTER_USERNAME')
        self.password = os.getenv('TWITTER_PASSWORD')
        self.logger = logging.getLogger(__name__)
        
        # Rate limiting configuration
        self.base_delay = 2  # Base delay in seconds
        self.max_delay = 300  # Maximum delay in seconds (5 minutes)
        self.endpoint_limits: Dict[str, EndpointRateLimit] = {}
        self.global_rate_limit = EndpointRateLimit(
            endpoint="global",
            requests_limit=150,  # Increased from 50 for 2000+ tweet collection
            reset_time=time.time() + 900
        )
        
        # Retry configuration
        self.max_retries = 5
        self.backoff_multiplier = 2.0  # Exponential backoff
        self.backoff_jitter = 0.1  # Random jitter (10%)
        
        # Statistics
        self.total_requests = 0
        self.rate_limit_hits = 0
        self.successful_retries = 0
    
    def wait_for_page_load(self, timeout=30):
        """Wait for page to fully load with tweets"""
        try:
            # Wait for tweets to appear
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="tweet"]'))
            )
            # Additional wait for content to stabilize
            time.sleep(2)
            return True
        except TimeoutException as e:
            self.logger.warning(f"Page load timeout: {e}")
            return False
        except Exception as e:
            self.logger.warning(f"Page load error: {e}")
            return False
    
    def detect_rate_limit_response(self) -> Optional[Dict]:
        """Detect rate limit from page content and response"""
        try:
            # Check for rate limit error messages on page
            rate_limit_indicators = [
                "Rate limit",
                "Too many requests",
                "Please wait",
                "Try again later",
                "Requests are coming in too fast"
            ]
            
            page_source = self.driver.page_source.lower()
            for indicator in rate_limit_indicators:
                if indicator.lower() in page_source:
                    self.logger.warning(f"Rate limit indicator detected: {indicator}")
                    return {"type": "page_content", "message": indicator}
            
            # Check for rate limit elements
            try:
                error_element = self.driver.find_element(
                    By.XPATH, 
                    "//*[contains(text(), 'rate limit') or contains(text(), 'too many')]"
                )
                if error_element:
                    self.logger.warning(f"Rate limit element found: {error_element.text}")
                    return {"type": "element", "message": error_element.text}
            except NoSuchElementException:
                pass
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Error detecting rate limit: {e}")
            return None
    
    def get_or_create_endpoint_limit(self, endpoint: str) -> EndpointRateLimit:
        """Get or create rate limit tracker for endpoint"""
        if endpoint not in self.endpoint_limits:
            self.endpoint_limits[endpoint] = EndpointRateLimit(
                endpoint=endpoint,
                requests_limit=100,
                reset_time=time.time() + 900
            )
        return self.endpoint_limits[endpoint]
    
    def check_rate_limit_status(self) -> RateLimitStatus:
        """Check current rate limit status"""
        remaining = self.global_rate_limit.requests_limit - self.global_rate_limit.requests_made
        limit_percentage = (self.global_rate_limit.requests_made / self.global_rate_limit.requests_limit) * 100
        
        if self.global_rate_limit.is_rate_limited():
            return RateLimitStatus.LIMITED
        elif limit_percentage >= 75:
            self.logger.info(f"[WARNING] Approaching rate limit: {remaining} requests remaining")
            return RateLimitStatus.APPROACHING
        
        return RateLimitStatus.OK
    
    def calculate_backoff_delay(self, attempt: int, reset_after: Optional[float] = None) -> float:
        """Calculate exponential backoff delay with jitter"""
        if reset_after:
            # Use Retry-After header value if provided
            return reset_after
        
        # Exponential backoff: base_delay * (multiplier ^ attempt)
        delay = self.base_delay * (self.backoff_multiplier ** attempt)
        
        # Add random jitter to prevent thundering herd
        jitter = delay * self.backoff_jitter * random.uniform(-1, 1)
        delay = max(self.base_delay, delay + jitter)
        
        # Cap maximum delay
        delay = min(delay, self.max_delay)
        
        return delay
    
    def apply_intelligent_rate_limit(self, endpoint: str = "general", action_type: str = "request"):
        """Apply intelligent rate limiting based on real conditions"""
        self.total_requests += 1
        
        # Get endpoint-specific limit
        ep_limit = self.get_or_create_endpoint_limit(endpoint)
        
        # Check if endpoint can accept requests
        while not ep_limit.can_request():
            reset_in = ep_limit.get_reset_in_seconds()
            self.logger.warning(
                f"[RATE_LIMIT] Endpoint '{endpoint}' rate limited. "
                f"Waiting {reset_in:.0f}s for reset..."
            )
            time.sleep(min(reset_in + 2, 300))  # Wait but cap at 5 minutes
        
        # Check global rate limit
        while not self.global_rate_limit.can_request():
            reset_in = self.global_rate_limit.get_reset_in_seconds()
            self.logger.warning(
                f"[RATE_LIMIT] Global limit hit. Waiting {reset_in:.0f}s..."
            )
            time.sleep(min(reset_in + 2, 300))  # Wait but cap at 5 minutes
        
        # Check rate limit status
        status = self.check_rate_limit_status()
        
        # Calculate adaptive delay based on status and action type
        if status == RateLimitStatus.LIMITED:
            delay = self.calculate_backoff_delay(ep_limit.backoff_count)
            self.logger.info(f"[BACKOFF] Backing off {delay:.2f}s")
            ep_limit.backoff_count = min(ep_limit.backoff_count + 1, ep_limit.max_backoff_count)
            self.rate_limit_hits += 1
            
        elif status == RateLimitStatus.APPROACHING:
            if action_type == "scroll":
                delay = random.uniform(3, 5)
            elif action_type == "search":
                delay = random.uniform(4, 6)
            else:
                delay = random.uniform(2, 4)
            
        else:
            # Normal operation
            if action_type == "scroll":
                delay = random.uniform(1.5, 2.5)
            elif action_type == "search":
                delay = random.uniform(2, 3)
            else:
                delay = random.uniform(1, 2)
        
        # Apply delay
        time.sleep(delay)
        
        # Record request
        ep_limit.record_request()
        self.global_rate_limit.record_request()
        
        self.logger.debug(
            f"Request #{self.total_requests} to {endpoint}. "
            f"Global: {self.global_rate_limit.requests_made}/"
            f"{self.global_rate_limit.requests_limit}, "
            f"Endpoint: {ep_limit.requests_made}/{ep_limit.requests_limit}"
        )
    
    def setup_driver(self):
        """Setup undetected Chrome driver"""
        options = uc.ChromeOptions()
        options.add_argument('--no-first-run')
        options.add_argument('--no-service-autorun')
        options.add_argument('--password-store=basic')
        
        self.driver = uc.Chrome(options=options, version_main=143, use_subprocess=False)
        
        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            '''
        })
    
    
    def human_type(self, element, text):
        """Type text with human-like delays and patterns to avoid detection"""
        chars_typed = 0
        for char in text:
            element.send_keys(char)
            
            # Variable typing speed - humans don't type uniformly
            base_delay = random.uniform(0.1, 0.3)  # Slower than before
            
            # Occasionally pause (like thinking or looking at keyboard)
            if chars_typed > 0 and chars_typed % random.randint(3, 5) == 0:
                time.sleep(random.uniform(0.5, 1.0))  # Thinking pause
            
            # Slower for special characters
            if char in '@._-':
                base_delay *= 1.5
            
            time.sleep(base_delay)
            chars_typed += 1
        
        # Small pause after finishing typing (like reviewing what was typed)
        time.sleep(random.uniform(0.3, 0.7))

    def login(self, max_attempts=3):
        """Robust Twitter login with proper page flow verification"""
    
        for attempt in range(max_attempts):
            try:
                # Fresh driver setup for each attempt
                if attempt > 0 or not self.driver:
                    self.logger.info(f"[LOGIN] Setting up driver for attempt {attempt + 1}...")
                    if self.driver:
                        try:
                            self.driver.quit()
                        except:
                            pass
                    self.setup_driver()

                self.logger.info(f"[LOGIN] Starting Twitter login (attempt {attempt + 1}/{max_attempts})...")

                self.driver.get("https://twitter.com/login")

                # Wait for page to be stable
                time.sleep(random.uniform(4, 6))

                # STEP 1: EMAIL INPUT WITH INTERNAL RETRY
                email_success = False
                for email_try in range(3):
                    try:
                        self.logger.debug(f"[LOGIN] Email step attempt {email_try + 1}/3...")
                        
                        email_input = WebDriverWait(self.driver, 30).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[autocomplete="username"]'))
                        )

                        email_input.clear()
                        # Little pause before typing again
                        time.sleep(random.uniform(0.5, 1.0))
                        self.human_type(email_input, self.email)

                        # Click NEXT
                        next_btn = WebDriverWait(self.driver, 15).until(
                            EC.element_to_be_clickable((By.XPATH, '//span[text()="Next"]'))
                        )

                        next_btn.click()
                        self.logger.debug("[LOGIN] Clicked Next after email")

                        # STEP 2: VERIFY PAGE MOVED FORWARD
                        try:
                            WebDriverWait(self.driver, 10).until(  # Shorter wait for internal retry
                                EC.any_of(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="password"]')),
                                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[data-testid="ocfEnterTextTextInput"]'))
                                )
                            )
                            self.logger.info("[LOGIN] Successfully moved past email step")
                            email_success = True
                            break

                        except TimeoutException:
                            # Check if still on email page
                            still_on_email = self.driver.find_elements(
                                By.CSS_SELECTOR, 'input[autocomplete="username"]'
                            )

                            if still_on_email:
                                self.logger.warning(f"[LOGIN] Email attempt {email_try + 1} failed - returned to email page. Retrying...")
                                time.sleep(random.uniform(2, 4))
                                continue
                            
                            self.logger.error("[LOGIN] Unknown page state after email step")
                            raise Exception("Unknown page state after email step")
                            
                    except Exception as e:
                        self.logger.warning(f"[LOGIN] Email internal retry {email_try + 1} error: {e}")
                        time.sleep(2)
                
                if not email_success:
                    self.logger.error("[LOGIN] All internal email attempts failed")
                    raise Exception("Email step failed after 3 internal attempts")

                time.sleep(random.uniform(2, 3))

                # STEP 3: HANDLE USERNAME VERIFICATION (IF ASKED)

                try:
                    username_input = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, 'input[data-testid="ocfEnterTextTextInput"]')
                        )
                    )

                    self.logger.info("[LOGIN] Username verification required")

                    username_input.clear()
                    self.human_type(username_input, self.username)

                    next_btn = WebDriverWait(self.driver, 15).until(
                        EC.element_to_be_clickable((By.XPATH, '//span[text()="Next"]'))
                    )

                    next_btn.click()
                    self.logger.debug("[LOGIN] Clicked Next after username")

                    time.sleep(random.uniform(2, 3))

                except TimeoutException:
                    self.logger.info("[LOGIN] Username verification not required")

                # STEP 4: PASSWORD INPUT

                self.logger.debug("[LOGIN] Waiting for password field...")

                password_input = WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="password"]'))
                )

                password_input.clear()
                self.human_type(password_input, self.password)

                login_btn = WebDriverWait(self.driver, 15).until(
                    EC.element_to_be_clickable((By.XPATH, '//span[text()="Log in"]'))
                )

                login_btn.click()
                self.logger.debug("[LOGIN] Clicked Log in button")

                # STEP 5: VERIFY LOGIN SUCCESS

                try:
                    WebDriverWait(self.driver, 30).until(
                        lambda d: "home" in d.current_url.lower() or "x.com/home" in d.current_url.lower()
                    )

                    self.logger.info(f"[SUCCESS] Login successful on attempt {attempt + 1}")
                    time.sleep(random.uniform(3, 5))
                    return True

                except TimeoutException:
                    self.logger.error("[LOGIN] Login button clicked but did not reach home page")
                    raise Exception("Login failed – did not reach home page")

            except Exception as e:
                self.logger.error(f"[ERROR] Login attempt {attempt + 1} failed: {e}")

                if attempt < max_attempts - 1:
                    delay = (attempt + 1) * 10
                    self.logger.info(f"[RETRY] Retrying login in {delay}s...")
                    time.sleep(delay)
                else:
                    self.logger.error("[FAILED] All login attempts exhausted")
                    return False

        return False



    # def login(self, max_attempts=3):
    #     """Login to Twitter with retry logic for improved reliability"""
    #     for attempt in range(max_attempts):
    #         try:
    #             # Recreate driver if session was lost
    #             if attempt > 0 or not self.driver:
    #                 self.logger.info(f"[LOGIN] Setting up driver for attempt {attempt + 1}...")
    #                 if self.driver:
    #                     try:
    #                         self.driver.quit()
    #                     except:
    #                         pass
    #                 self.setup_driver()
                
    #             self.logger.info(f"[LOGIN] Starting Twitter login (attempt {attempt + 1}/{max_attempts})...")
                
    #             self.driver.get("https://twitter.com/login")
    #             time.sleep(random.uniform(5, 7))
                
    #             # Email - increased timeout to 30 seconds
    #             email_input = WebDriverWait(self.driver, 30).until(
    #                 EC.presence_of_element_located((By.CSS_SELECTOR, 'input[autocomplete="username"]'))
    #             )
                
    #             # Type email with human-like delays
    #             self.human_type(email_input, self.email)
                
    #             # Click Next button with proper wait
    #             next_btn = WebDriverWait(self.driver, 15).until(
    #                 EC.element_to_be_clickable((By.XPATH, '//span[text()="Next"]'))
    #             )
    #             self.logger.debug("[LOGIN] Email field found, clicking Next")
    #             next_btn.click()
    #             self.logger.debug("[LOGIN] Clicked Next after email, waiting for next page...")
    #             time.sleep(random.uniform(3, 5))
                
    #             # Username if required
    #             try:
    #                 username_input = WebDriverWait(self.driver, 5).until(
    #                     EC.presence_of_element_located((By.CSS_SELECTOR, 'input[data-testid="ocfEnterTextTextInput"]'))
    #                 )
    #                 self.logger.info("[USERNAME] Username verification required")
    #                 self.human_type(username_input, self.username)
                    
    #                 next_btn = WebDriverWait(self.driver, 15).until(
    #                     EC.element_to_be_clickable((By.XPATH, '//span[text()="Next"]'))
    #                 )
    #                 next_btn.click()
    #                 self.logger.debug("[LOGIN] Clicked Next after username")
    #                 time.sleep(random.uniform(3, 5))
    #             except TimeoutException:
    #                 # Username step not required
    #                 self.logger.info("[LOGIN] Username field not required, looking for password...")
    #             except Exception as e:
    #                 self.logger.debug(f"[LOGIN] Username handling error: {e}")
                
    #             # Password - try multiple selectors with increased timeout
    #             self.logger.debug("[LOGIN] Looking for password field...")
    #             password_input = None
    #             password_selectors = [
    #                 (By.CSS_SELECTOR, 'input[name="password"]'),
    #                 (By.CSS_SELECTOR, 'input[type="password"]'),
    #                 (By.XPATH, '//input[@autocomplete="current-password"]')
    #             ]
                
    #             for selector_type, selector_value in password_selectors:
    #                 try:
    #                     password_input = WebDriverWait(self.driver, 30).until(
    #                         EC.presence_of_element_located((selector_type, selector_value))
    #                     )
    #                     self.logger.debug(f"[LOGIN] Password field found with selector: {selector_value}")
    #                     break
    #                 except TimeoutException:
    #                     continue
                
    #             if not password_input:
    #                 raise TimeoutException("Password field not found with any selector")
                
    #             self.human_type(password_input, self.password)
                
    #             login_btn = WebDriverWait(self.driver, 15).until(
    #                 EC.element_to_be_clickable((By.XPATH, '//span[text()="Log in"]'))
    #             )
    #             login_btn.click()
    #             self.logger.debug("[LOGIN] Clicked Log in button")
                
    #             # Wait for login to complete with explicit check for home page
    #             self.logger.debug("[LOGIN] Waiting for redirect to home page...")
    #             WebDriverWait(self.driver, 30).until(
    #                 lambda driver: "home" in driver.current_url.lower() or "x.com/home" in driver.current_url.lower()
    #             )
                
    #             self.logger.info(f"[SUCCESS] Login successful on attempt {attempt + 1}")
    #             time.sleep(random.uniform(3, 5))  # Additional stabilization time
    #             return True
                    
    #         except TimeoutException as e:
    #             self.logger.warning(f"[LOGIN] Timeout on attempt {attempt + 1}: {e}")
    #             if attempt < max_attempts - 1:
    #                 delay = (attempt + 1) * 10  # Progressive delay: 10s, 20s, 30s
    #                 self.logger.info(f"[RETRY] Retrying login in {delay}s...")
    #                 time.sleep(delay)
    #             else:
    #                 self.logger.error("[ERROR] Login failed after all attempts")
    #                 return False
    #         except Exception as e:
    #             self.logger.error(f"[ERROR] Login error on attempt {attempt + 1}: {type(e).__name__}: {e}")
    #             if attempt < max_attempts - 1:
    #                 delay = (attempt + 1) * 10
    #                 self.logger.info(f"[RETRY] Retrying login in {delay}s...")
    #                 time.sleep(delay)
    #             else:
    #                 return False
        
    #     return False
    
    def scrape_hashtag_with_retry(self, hashtag, max_tweets=750, max_retries=3):
        """Scrape hashtag with advanced retry logic for realistic rate limiting"""
        for attempt in range(max_retries):
            try:
                self.logger.info(f"Scraping #{hashtag} (attempt {attempt + 1}/{max_retries})")
                tweets = self.scrape_hashtag(hashtag, max_tweets)
                
                if tweets:
                    self.logger.info(f"[SUCCESS] Successfully scraped #{hashtag} with {len(tweets)} tweets")
                    if attempt > 0:
                        self.successful_retries += 1
                    return tweets
                else:
                    self.logger.warning(f"[WARNING] No tweets collected for #{hashtag} on attempt {attempt + 1}")
                    
            except RateLimitException as e:
                self.logger.error(f"Rate limit error scraping #{hashtag}: {e}")
                
                # Handle rate limit with intelligent backoff
                if attempt < max_retries - 1:
                    delay = self.calculate_backoff_delay(attempt, e.reset_after)
                    self.logger.info(
                        f"[RATE_LIMIT] Rate limited. Retrying #{hashtag} in {delay:.1f} seconds "
                        f"(attempt {attempt + 2}/{max_retries})"
                    )
                    time.sleep(delay)
                    
            except Exception as e:
                self.logger.error(f"Error scraping #{hashtag} on attempt {attempt + 1}: {e}")
                
                # General backoff for other errors
                if attempt < max_retries - 1:
                    delay = self.calculate_backoff_delay(attempt)
                    self.logger.info(f"Retrying #{hashtag} in {delay:.1f} seconds...")
                    time.sleep(delay)
        
        self.logger.error(f"[FAILED] Failed to scrape #{hashtag} after {max_retries} attempts")
        return []
    
    def scrape_hashtag(self, hashtag, max_tweets=750):
        """Scrape tweets for specific hashtag with intelligent rate limiting and progressive patience"""
        try:
            search_url = f"https://twitter.com/search?q=%23{hashtag}&src=typed_query&f=live"
            
            self.driver.get(search_url)
            
            # Wait for page to load completely
            if not self.wait_for_page_load():
                self.logger.error(f"Failed to load search page for #{hashtag}")
                
                # Check if it's a rate limit issue
                rate_limit_response = self.detect_rate_limit_response()
                if rate_limit_response:
                    self.logger.error(f"Rate limit detected: {rate_limit_response}")
                    raise RateLimitException(
                        f"Rate limit detected for #{hashtag}: {rate_limit_response['message']}"
                    )
                return []
            
            # Apply rate limit after page loaded successfully
            self.apply_intelligent_rate_limit(f"search/{hashtag}", "search")
            
            self.logger.info(f"Search page loaded for #{hashtag}")
            
            tweets = []
            seen_texts = set()
            scroll_count = 0
            max_scrolls = 500  # Very high limit - only stop if we truly can't get more tweets
            no_new_tweets_count = 0
            consecutive_rate_limits = 0
            
            # Progressive patience: more patient as we collect more tweets
            def get_patience_threshold(current_count):
                """Return how many empty scrolls to tolerate based on current tweet count"""
                if current_count < 100:
                    return 20  # Early stage: stop after 20 empty scrolls
                elif current_count < 300:
                    return 40  # Mid stage: stop after 40 empty scrolls
                elif current_count < 500:
                    return 60  # Late stage: stop after 60 empty scrolls
                else:
                    return 100  # Final push: stop after 100 empty scrolls
            
            while len(tweets) < max_tweets and scroll_count < max_scrolls:
                # Check for rate limit response
                rate_limit_response = self.detect_rate_limit_response()
                if rate_limit_response:
                    consecutive_rate_limits += 1
                    if consecutive_rate_limits > 2:
                        self.logger.error(f"Multiple rate limit hits detected for #{hashtag}")
                        raise RateLimitException(f"Repeated rate limit for #{hashtag}")
                    # Continue but with increased delay
                    self.logger.warning(f"Rate limit detected during scroll {scroll_count}")
                    time.sleep(self.calculate_backoff_delay(consecutive_rate_limits - 1))
                else:
                    consecutive_rate_limits = 0
                
                tweet_elements = self.driver.find_elements(By.CSS_SELECTOR, '[data-testid="tweet"]')
                initial_count = len(tweets)
                
                for tweet in tweet_elements:
                    try:
                        # Extract text
                        text_element = tweet.find_element(By.CSS_SELECTOR, '[data-testid="tweetText"]')
                        text = text_element.text.strip()
                        
                        if not text or text in seen_texts:
                            continue
                        
                        seen_texts.add(text)
                        
                        # Extract username
                        try:
                            username_element = tweet.find_element(By.CSS_SELECTOR, '[data-testid="User-Name"] a')
                            username = username_element.get_attribute('href').split('/')[-1]
                        except Exception:
                            username = "unknown"
                        
                        # Extract engagement metrics
                        try:
                            replies = tweet.find_element(By.CSS_SELECTOR, '[data-testid="reply"]').text or "0"
                            retweets = tweet.find_element(By.CSS_SELECTOR, '[data-testid="retweet"]').text or "0"
                            likes = tweet.find_element(By.CSS_SELECTOR, '[data-testid="like"]').text or "0"
                        except Exception:
                            replies = retweets = likes = "0"
                        
                        # Extract hashtags and mentions
                        hashtags = [word for word in text.split() if word.startswith('#')]
                        mentions = [word for word in text.split() if word.startswith('@')]
                        
                        tweet_data = {
                            'username': username,
                            'text': text,
                            'hashtag': hashtag,
                            'hashtags': hashtags,
                            'mentions': mentions,
                            'replies': replies,
                            'retweets': retweets,
                            'likes': likes,
                            'timestamp': datetime.now().isoformat(),
                            'scraped_at': time.time()
                        }
                        
                        tweets.append(tweet_data)
                        
                        if len(tweets) >= max_tweets:
                            break
                            
                    except Exception as e:
                        self.logger.debug(f"Error extracting tweet data: {e}")
                        continue
                
                # Check if we got new tweets
                if len(tweets) == initial_count:
                    no_new_tweets_count += 1
                    patience = get_patience_threshold(len(tweets))
                    
                    # Log progress when struggling to find tweets
                    if no_new_tweets_count % 5 == 0:
                        self.logger.info(
                            f"#{hashtag}: {len(tweets)} tweets, {no_new_tweets_count}/{patience} empty scrolls"
                        )
                    
                    # Stop if we've exhausted the feed
                    if no_new_tweets_count >= patience:
                        self.logger.info(
                            f"No new tweets for {patience} consecutive scrolls at {len(tweets)} tweets. "
                            f"Feed exhausted for #{hashtag}."
                        )
                        break
                else:
                    no_new_tweets_count = 0
                
                # Scroll down with adaptive delays
                status = self.check_rate_limit_status()
                if status == RateLimitStatus.LIMITED:
                    # We're already rate limited, apply exponential backoff
                    delay = self.calculate_backoff_delay(self.global_rate_limit.backoff_count)
                    self.logger.warning(f"[BACKOFF] Rate limited during scrolling. Backing off {delay:.1f}s")
                    time.sleep(delay)
                    self.global_rate_limit.backoff_count = min(
                        self.global_rate_limit.backoff_count + 1,
                        self.global_rate_limit.max_backoff_count
                    )
                elif status == RateLimitStatus.APPROACHING:
                    # Approaching limit, use conservative scroll delay
                    delay = random.uniform(3.5, 5)
                    self.logger.debug(f"[CONSERVATIVE] Approaching rate limit. Conservative delay: {delay:.1f}s")
                    time.sleep(delay)
                else:
                    # Normal operation - increased delays for better content loading
                    if no_new_tweets_count > 5:
                        # If struggling to find tweets, wait longer
                        delay = random.uniform(4, 6)
                        self.logger.debug(f"[PATIENT] Struggling to find tweets. Extended delay: {delay:.1f}s")
                    else:
                        delay = random.uniform(2.5, 3.5)  # Increased from 1.5-2.5
                    time.sleep(delay)
                
                # Scroll to bottom
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                
                # Wait for new tweets to load after scroll - increased wait time
                time.sleep(random.uniform(2, 3))  # Increased from 1-2
                
                # Check if new content loaded
                new_tweet_elements = self.driver.find_elements(By.CSS_SELECTOR, '[data-testid="tweet"]')
                if len(new_tweet_elements) == len(tweet_elements):
                    # No new tweets loaded, wait a bit more
                    self.logger.debug("No new tweets loaded after scroll, waiting longer...")
                    time.sleep(2)  # Increased from 1
                
                scroll_count += 1
                
                # Log progress every 10 scrolls
                if scroll_count % 10 == 0:
                    self.logger.info(
                        f"#{hashtag}: {len(tweets)} tweets collected (scroll {scroll_count}) | "
                        f"Rate limit status: {self.check_rate_limit_status().value}"
                    )
            
            self.logger.info(f"[SUCCESS] Collected {len(tweets)} tweets for #{hashtag}")
            return tweets
            
        except RateLimitException:
            raise
            
        except Exception as e:
            self.logger.error(f"Scraping error for #{hashtag}: {e}")
            return []
    
    def scrape_multiple_hashtags(self, hashtags, tweets_per_hashtag=750):
        """Scrape multiple hashtags with intelligent rate limiting between them"""
        try:
            # LOGIN - driver will be created automatically
            if not self.login():
                self.logger.error("[ERROR] Login failed. Cannot proceed.")
                return []
            
            all_tweets = []
            
            for i, hashtag in enumerate(hashtags, 1):
                self.logger.info(f"\n[SCRAPE] Scraping #{hashtag} ({i}/{len(hashtags)})...")
                
                try:
                    tweets = self.scrape_hashtag_with_retry(hashtag, tweets_per_hashtag)
                    all_tweets.extend(tweets)
                    
                    self.logger.info(
                        f"[PROGRESS] Progress: {len(all_tweets)} total tweets | "
                        f"Rate limits hit: {self.rate_limit_hits} | "
                        f"Successful retries: {self.successful_retries}"
                    )
                    
                except RateLimitException as e:
                    self.logger.error(f"Failed to scrape #{hashtag} due to rate limiting: {e}")
                    continue
                
                # Intelligent rate limiting between hashtags
                if i < len(hashtags):
                    # Calculate delay based on rate limit status
                    status = self.check_rate_limit_status()
                    
                    if status == RateLimitStatus.LIMITED:
                        # Already rate limited, wait longer
                        delay = self.calculate_backoff_delay(2)
                        self.logger.warning(
                            f"[RATE_LIMIT] Rate limited. Waiting {delay:.1f}s before next hashtag..."
                        )
                    elif status == RateLimitStatus.APPROACHING:
                        # Approaching limit, be conservative
                        delay = random.uniform(10, 15)
                        remaining = self.global_rate_limit.requests_limit - self.global_rate_limit.requests_made
                        self.logger.info(
                            f"[WARNING] Approaching rate limit. "
                            f"{remaining} requests remaining. "
                            f"Waiting {delay:.1f}s before next hashtag..."
                        )
                    else:
                        # Normal operation, minimal delay between hashtags
                        delay = random.uniform(5, 8)
                        self.logger.info(f"[WAIT] Waiting {delay:.1f}s before next hashtag...")
                    
                    time.sleep(delay)
            
            # Print final statistics
            self.logger.info("\n" + "="*60)
            self.logger.info("[COMPLETE] SCRAPING COMPLETE - STATISTICS")
            self.logger.info("="*60)
            self.logger.info(f"Total tweets collected: {len(all_tweets)}")
            self.logger.info(f"Total requests made: {self.total_requests}")
            self.logger.info(f"Rate limit hits: {self.rate_limit_hits}")
            self.logger.info(f"Successful retries: {self.successful_retries}")
            self.logger.info(f"Final rate limit status: {self.check_rate_limit_status().value}")
            
            # Print endpoint statistics
            self.logger.info("\nEndpoint Statistics:")
            for endpoint, limit in self.endpoint_limits.items():
                self.logger.info(
                    f"  {endpoint}: {limit.requests_made}/{limit.requests_limit} requests"
                )
            
            self.logger.info("="*60 + "\n")
            
            return all_tweets
            
        except Exception as e:
            self.logger.error(f"[ERROR] Scraping pipeline error: {e}")
            return []
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                    self.logger.info("[SUCCESS] Browser closed")
                except Exception as e:
                    self.logger.warning(f"Error closing driver: {e}")
    
    def close(self):
        """Properly close the webdriver"""
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
            except Exception as e:
                self.logger.warning(f"Error closing driver: {e}")
