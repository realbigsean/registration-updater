import requests
import json
import time
import logging
import argparse
import sys

# Configure logging to stdout only
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("flashbots_validator_tracker")

class FlashbotsValidatorTracker:
    def __init__(self, config):
        self.source_relay = config["source_relay"]
        # Ensure source relay URL has the correct path
        if not self.source_relay.endswith("/relay/v1/builder/validators"):
            self.source_relay = self.source_relay.rstrip("/") + "/relay/v1/builder/validators"
            
        self.target_relay = config["target_relay"]
        self.interval = config["interval"]
        self.validators = None  # Store validators in memory
        
        logger.info(f"Initialized tracker: source={self.source_relay}, target={self.target_relay}, interval={self.interval}s")
    
    def fetch_validators(self):
        """Fetch validator registrations from Flashbots relay"""
        try:
            logger.info(f"Fetching validators from {self.source_relay}")
            
            response = requests.get(
                self.source_relay,
                headers={"Accept": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Successfully fetched {len(data)} validators")
                
                # Check for changes
                if self.validators is not None:
                    changes = self.detect_changes(self.validators, data)
                    if changes["added"] or changes["removed"] or changes["updated"]:
                        logger.info(f"Changes detected: {len(changes['added'])} added, {len(changes['removed'])} removed, {len(changes['updated'])} updated")
                        post_success = self.post_to_target(data)
                        
                        # Only update stored validators if posting was successful
                        if post_success:
                            self.validators = data
                            logger.info("Updated stored validators after successful post")
                        else:
                            logger.warning("Not caching validator changes due to failed post")
                    else:
                        logger.info("No changes detected")
                else:
                    # First run, post everything
                    logger.info("First fetch, posting all validators")
                    post_success = self.post_to_target(data)
                    
                    # Only update stored validators if posting was successful
                    if post_success:
                        self.validators = data
                        logger.info("Updated stored validators after successful post")
                    else:
                        logger.warning("Not storing initial validators due to failed post")
                
                return data
            else:
                logger.error(f"Failed to fetch validators: {response.status_code} {response.reason}")
                logger.error(f"Response: {response.text[:200]}...")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching validators: {str(e)}")
            return None
    
    def transform_data_format(self, data):
        """Transform data to match the target API's expected format"""
        try:
            # Log a sample of the original data for debugging
            if data and len(data) > 0:
                logger.info(f"Original data sample structure: {json.dumps(data[0], indent=2)[:200]}...")
                
            # Transform from the GET format to the POST format
            # GET format: [{"slot": "1", "validator_index": "1", "entry": {"message": {...}, "signature": "..."}}]
            # POST format: [{"message": {...}, "signature": "..."}]
            transformed_data = []
            
            for item in data:
                if "entry" in item and "message" in item["entry"] and "signature" in item["entry"]:
                    # Extract the message and signature from the entry
                    transformed_item = {
                        "message": item["entry"]["message"],
                        "signature": item["entry"]["signature"]
                    }
                    transformed_data.append(transformed_item)
                else:
                    logger.warning(f"Item doesn't match expected structure: {json.dumps(item)[:100]}...")
            
            logger.info(f"Transformed {len(data)} records into {len(transformed_data)} records for target API")
            if transformed_data and len(transformed_data) > 0:
                logger.info(f"Transformed data sample: {json.dumps(transformed_data[0], indent=2)[:200]}...")
                
            return transformed_data
        except Exception as e:
            logger.error(f"Error transforming data: {str(e)}")
            # Return the original data if transformation fails
            return data
    
    def post_to_target(self, data):
        """Post validator data to target relay"""
        try:
            # Transform data to match the target API's expected format
            transformed_data = self.transform_data_format(data)
            
            logger.info(f"Posting {len(transformed_data)} validators to {self.target_relay}")
            
            # Print a snippet of the payload for debugging
            if transformed_data and len(transformed_data) > 0:
                payload_snippet = json.dumps(transformed_data[0], indent=2)[:200]
                logger.info(f"Payload sample: {payload_snippet}...")
            
            response = requests.post(
                f"{self.target_relay}/eth/v1/builder/validators",
                json=transformed_data,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code in [200, 201, 202]:
                logger.info(f"Successfully posted data: {response.status_code}")
                return True
            else:
                logger.error(f"Failed to post data: {response.status_code} {response.reason}")
                logger.error(f"Response: {response.text[:200]}...")
                # Log the full error response for debugging
                try:
                    error_detail = response.json()
                    logger.error(f"Error details: {json.dumps(error_detail, indent=2)}")
                except:
                    pass
                return False
                
        except Exception as e:
            logger.error(f"Error posting to target relay: {str(e)}")
            return False
    
    def detect_changes(self, old_data, new_data):
        """Detect changes between validator sets"""
        # Extract pubkeys for comparison
        old_keys = {item["entry"]["message"]["pubkey"]: item for item in old_data}
        new_keys = {item["entry"]["message"]["pubkey"]: item for item in new_data}
        
        # Find differences
        added_keys = set(new_keys) - set(old_keys)
        removed_keys = set(old_keys) - set(new_keys)
        common_keys = set(old_keys) & set(new_keys)
        
        # Check for updates
        updated = []
        for key in common_keys:
            if json.dumps(old_keys[key], sort_keys=True) != json.dumps(new_keys[key], sort_keys=True):
                updated.append(key)
        
        return {
            "added": [new_keys[k] for k in added_keys],
            "removed": [old_keys[k] for k in removed_keys],
            "updated": [new_keys[k] for k in updated]
        }
    
    def run(self):
        """Main loop to fetch and forward validator data"""
        logger.info(f"Starting validator tracking (interval: {self.interval}s)")
        
        try:
            while True:
                self.fetch_validators()
                time.sleep(self.interval)
        except KeyboardInterrupt:
            logger.info("Stopped by user")
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            sys.exit(1)

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Track and forward Flashbots validator registrations")
    
    parser.add_argument("--target-relay", "-t", required=True, 
                        help="URL of target relay to forward validator data")
    parser.add_argument("--source-relay", "-s", 
                        default="https://0xafa4c6985aa049fb79dd37010438cfebeb0f2bd42b115b89dd678dab0670c1de38da0c4e9138c9290a398ecd9a0b3110@boost-relay.flashbots.net",
                        help="URL of Flashbots relay (default: %(default)s)")
    parser.add_argument("--interval", "-i", type=int, default=6,  # 6 seconds
                        help="Polling interval in seconds (default: %(default)s)")
    parser.add_argument("--debug", "-d", action="store_true",
                        help="Enable detailed debug logging")
    
    args = parser.parse_args()
    
    # Set debug logging if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    # Create and run tracker
    config = {
        "source_relay": args.source_relay,
        "target_relay": args.target_relay,
        "interval": args.interval
    }
    
    tracker = FlashbotsValidatorTracker(config)
    tracker.run()

if __name__ == "__main__":
    main()
