from typing import Dict, Any, Optional, List
import spacy
import re
from datetime import datetime, timedelta
import dateparser
import json
from pathlib import Path

class EmailParser:
    def __init__(self):
        try:
            self.nlp = spacy.load("./custom_model")
            # Load custom configuration
            config_path = Path("./custom_model/config.json")
            if config_path.exists():
                with open(config_path, "r") as f:
                    self.config = json.load(f)
            else:
                self.config = {}
        except Exception as e:
            print(f"Custom model not found, using base model: {e}")
            self.nlp = spacy.load("en_core_web_sm")
            self.config = {}

    def parse_email(self, email_text: str) -> Dict[str, Any]:
        # Extract header information
        headers = self._extract_headers(email_text)
        
        # Get classification
        doc = self.nlp(email_text)
        cats = doc.cats if hasattr(doc, 'cats') else {}
        
        # Determine reply types with confidence scores
        reply_types = sorted(cats.items(), key=lambda x: x[1], reverse=True)
        reply_type_scores = {k: v for k, v in reply_types if v > 0.3}
        time_info = self.extract_time_info(doc, email_text)
        
        # Determine primary type with proper fallback
        primary_type = "unknown"
        if reply_types:  # Only access if list is not empty
            primary_type = reply_types[0][0]
        
        # Check for combined types with improved logic
        if len(reply_type_scores) > 1:
            if ("reschedule" in reply_type_scores and "delegation" in reply_type_scores) or \
               ("delegation" in reply_type_scores and "reschedule" in reply_type_scores):
                primary_type = "reschedule_with_delegation"
        
        # Extract all information
        additional_info = self._extract_additional_info(doc)
        proposed_time = self.determine_most_probable_time(
            time_info.get("original_time"),
            time_info.get("proposed_times", []),
            email_text
        )
        meeting_link = self._extract_link(doc)
        delegate_info = self._extract_delegate(doc)
        
        # Format additional notes
        notes = []
        if time_info.get("uncertainty"):
            notes.append("Schedule uncertainty indicated")
        if time_info.get("alternative_times_suggested"):
            times_str = ", ".join(time_info.get("proposed_times", []))
            notes.append(f"Alternative times suggested: {times_str}")
        if time_info.get("original_time"):
            notes.append(f"Original time was {time_info['original_time']}")
        
        # Combine all extracted information
        result = {
            "from_email": headers.get("from"),
            "to_email": headers.get("to"),
            "subject": headers.get("subject"),
            "reply_type": primary_type,
            "reply_type_scores": reply_type_scores,
            "proposed_time": proposed_time,  # Now properly set for delegation cases
            "meeting_link": meeting_link,
            "delegate_to": delegate_info.get("delegate_email") if isinstance(delegate_info, dict) else delegate_info,
            "additional_info": time_info,
            "additional_notes": "\n".join(f"- {note}" for note in notes) if notes else None,
            "processed_at": datetime.utcnow().isoformat(),
            "_raw_text": email_text  # Add raw text for context processing
        }
        
        return result

    def _extract_headers(self, email_text: str) -> Dict[str, str]:
        headers = {}
        header_patterns = {
            "from": r"From: ([^\n]+)",
            "to": r"To: ([^\n]+)",
            "subject": r"Subject: ([^\n]+)"
        }
        
        for key, pattern in header_patterns.items():
            match = re.search(pattern, email_text)
            headers[key] = match.group(1).strip() if match else None
            
        return headers

    def _extract_time(self, doc) -> Optional[str]:
        """Extract time information from text"""
        text = doc.text
        time_patterns = [
            r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(?:at|@)?\s*\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)',
            r'\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)\s+(?:on\s+)?(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)',
            r'next\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(?:at|@)?\s*\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)',
            r'tomorrow\s+(?:at|@)?\s*\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)',
            r'\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)'
        ]
        
        for pattern in time_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    date_str = match.group()
                    parsed_date = dateparser.parse(date_str, settings={
                        'PREFER_DATES_FROM': 'future'
                    })
                    if parsed_date:
                        return parsed_date.isoformat()
                except Exception as e:
                    print(f"Error parsing date: {e}")
                    continue
        return None

    def _extract_link(self, doc) -> Optional[str]:
        """Extract meeting links from text"""
        text = doc.text
        link_patterns = [
            r'https?://(?:[\w-]+\.)*(?:webinar|zoom|teams|meet|calendly)\.(?:com|us|net)/\S+',
            r'https?://\S+\.(?:com|us|net)/(?:meet|join|reschedule|webinar|conference)\S*'
        ]
        
        for pattern in link_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group()
        return None

    def _extract_delegate(self, doc) -> Optional[str]:
        """Extract delegate email from text"""
        text = doc.text
        delegate_patterns = [
            r'my associate,?\s*(?:\w+)?\s*\(([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,})\)',
            r'delegate\s+to\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,})',
            r'(?:my|the)\s+associate,?\s*(\w+)\s*\(([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,})\)',
            r'(?:my|the)\s+associate,?\s*(\w+)\s*(?:\([^)]*\))?,?\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,})',
            r'step\s+in[^.]*?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,})',
            r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,})\s*(?:can|will|should|to)\s+(?:handle|take over|step in)'
        ]
        
        for pattern in delegate_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Return the last group that matches an email pattern
                for group in match.groups()[::-1]:
                    if group and '@' in group:
                        return group
        return None

    def _extract_additional_info(self, doc) -> Dict[str, Any]:
        """Extract structured additional information using model's custom patterns"""
        text = doc.text.lower()
        info = {
            "uncertainty": False,
            "alternative_times_suggested": False,
            "delegate_name": None,
            "delegate_email": None,
            "original_time": None,
            "proposed_times": []
        }
        
        # Use patterns from model config if available
        uncertainty_patterns = self.config.get("custom_patterns", {}).get("uncertainty", [
            r"high chance",
            r"depending on",
            r"might be able",
            r"not sure",
            r"possibly",
            r"tentative"
        ])
        
        # Check uncertainty using model's patterns
        info["uncertainty"] = any(re.search(pattern, text) for pattern in uncertainty_patterns)
        
        # Extract times with improved patterns
        time_info = self.extract_time_info(doc, text)
        info.update(time_info)
        
        # Extract delegate information with improved patterns
        delegate_info = self._extract_delegate_info(text)
        if delegate_info:
            info.update(delegate_info)
        
        return info

    def extract_time_info(self, doc, text) -> Dict[str, Any]:
        """Extract time-related information from the email"""
        additional_info = {
            "uncertainty": False,
            "alternative_times_suggested": False,
            "delegate_name": None,
            "delegate_email": None,
            "original_time": None,
            "proposed_times": []
        }
        
        try:
            found_times = []
            today = datetime.now()
            
            # First look for explicit weekday + time patterns
            weekday_pattern = r"((?:next\s+)?(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)(?:day)?)\s+(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm))"
            weekday_matches = re.finditer(weekday_pattern, text, re.IGNORECASE)
            
            for match in weekday_matches:
                weekday_str = match.group(1).lower()
                time_str = match.group(2)
                
                parsed_time = self._parse_weekday_time(weekday_str, time_str, today)
                if parsed_time:
                    found_times.append(parsed_time)
            
            # Then look for time confirmations
            confirmation_pattern = r"(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm))\s+(?:works|is fine|is good|is perfect|is set|confirmed)"
            conf_matches = re.finditer(confirmation_pattern, text, re.IGNORECASE)
            
            for match in conf_matches:
                time_str = match.group(1)
                parsed_time = dateparser.parse(time_str, settings={
                    'PREFER_DATES_FROM': 'future',
                    'RELATIVE_BASE': today
                })
                if parsed_time:
                    found_times.append(parsed_time)
            
            if found_times:
                additional_info["original_time"] = found_times[0].isoformat()
                if len(found_times) > 1:
                    additional_info["proposed_times"] = [t.isoformat() for t in found_times[1:]]
                    additional_info["alternative_times_suggested"] = True
            
        except Exception as e:
            print(f"Error in time extraction: {str(e)}")
            
        return additional_info

    def _extract_delegate_info(self, text: str) -> Optional[Dict[str, str]]:
        """Enhanced delegate information extraction"""
        patterns = [
            r"(?:my|the)\s+associate,?\s*(\w+)\s*\(([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,})\)",
            r"(?:my|the)\s+associate,?\s*(\w+)[^(]*?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,})"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return {
                    "delegate_name": match.group(1),
                    "delegate_email": match.group(2)
                }
        return None

    def _extract_additional_notes(self, doc, additional_info: Dict[str, Any]) -> Optional[str]:
        """Generate comprehensive additional notes"""
        notes = []
        
        if additional_info["uncertainty"]:
            notes.append("- Schedule uncertainty indicated")
        
        if additional_info["alternative_times_suggested"]:
            notes.append(f"- Alternative times suggested: {', '.join(additional_info['proposed_times'])}")
        
        if additional_info["delegate_name"] and additional_info["delegate_email"]:
            notes.append(f"- Delegation arranged to {additional_info['delegate_name']} ({additional_info['delegate_email']})")
        
        if additional_info["original_time"]:
            notes.append(f"- Original time was {additional_info['original_time']}")
        
        # Add any custom notes from model's user_data if available
        if hasattr(doc, 'user_data') and doc.user_data.get('custom_notes'):
            notes.extend(doc.user_data['custom_notes'])
        
        return "\n".join(notes) if notes else None

    def determine_most_probable_time(self, original_time: str, proposed_times: List[str], text: str) -> Optional[str]:
        """
        Determine the most probable proposed time based on context and patterns
        """
        # Early returns if no times to process
        if not proposed_times and not original_time:
            return None
        if not proposed_times:
            return original_time
        
        # Convert times to datetime objects for comparison
        times = [dateparser.parse(t) for t in proposed_times if t]
        if not times:
            return original_time if original_time else None
        
        # If only one time, return it
        if len(times) == 1:
            return times[0].isoformat()
        
        # Scoring system for each proposed time
        time_scores = {}
        orig_dt = dateparser.parse(original_time) if original_time else None
        
        for dt in times:
            if not dt:  # Skip if datetime parsing failed
                continue
            
            score = 0.0
            
            try:
                # Specific mention patterns and their weights
                month = dt.strftime('%B')
                day = dt.strftime('%d').lstrip('0')
                hour = dt.strftime('%I').lstrip('0')
                ampm = dt.strftime('%p')
                
                patterns = {
                    f"{month}.*?{day}": 0.8,
                    f"{hour}.*?{ampm}": 0.6,
                    r"prefer": 0.7,
                    r"suggest": 0.6,
                    r"recommend": 0.7,
                    r"better": 0.5,
                    r"ideal": 0.8,
                    r"good": 0.4
                }
                
                # Check for pattern matches
                for pattern, weight in patterns.items():
                    if re.search(pattern, text, re.IGNORECASE):
                        score += weight
                
                # If original time exists, add contextual scoring
                if orig_dt:
                    if dt.date() == orig_dt.date():
                        score += 0.3
                    if 9 <= dt.hour <= 17:
                        score += 0.2
                    if dt > orig_dt:
                        score += 0.4
                    
                time_scores[dt] = score
                
            except Exception as e:
                print(f"Error scoring time {dt}: {str(e)}")
                continue
        
        # Return most probable time if we have scores, otherwise fall back to original
        if time_scores:
            most_probable = max(time_scores.items(), key=lambda x: x[1])[0]
            return most_probable.isoformat()
        
        return original_time if original_time else None

    def split_emails(self, text: str) -> List[str]:
        """Split a thread of emails into individual emails"""
        # Split on 'From:' but keep the delimiter
        emails = re.split(r'(?=From:)', text)
        # Filter out empty strings and strip whitespace
        return [email.strip() for email in emails if email.strip()]

    def parse_email_thread(self, thread_text: str) -> List[Dict[str, Any]]:
        """Parse a thread of emails"""
        emails = self.split_emails(thread_text)
        parsed_emails = []
        
        # Parse each email in reverse chronological order (most recent first)
        for email in reversed(emails):
            parsed = self.parse_email(email)
            parsed_emails.append(parsed)
        
        # Process the thread context
        for i in range(len(parsed_emails)):
            if i > 0:
                # Reference previous email's times for context
                prev_email = parsed_emails[i-1]
                current_email = parsed_emails[i]
                
                # If current email confirms a time from previous email
                if prev_email["proposed_time"] and not current_email["proposed_time"]:
                    time_mentioned = self._find_time_confirmation(
                        current_email["additional_info"].get("original_time"),
                        prev_email["proposed_time"],
                        current_email["_raw_text"]  # Need to add this to parse_email output
                    )
                    if time_mentioned:
                        current_email["proposed_time"] = time_mentioned
                        current_email["additional_info"]["original_time"] = time_mentioned
        
        return parsed_emails

    def _find_time_confirmation(self, current_time: Optional[str], prev_time: str, text: str) -> Optional[str]:
        """Check if the current email confirms a time from the previous email"""
        if not prev_time:
            return current_time
        
        prev_dt = dateparser.parse(prev_time)
        if not prev_dt:
            return current_time
        
        # Look for confirmation of the specific time
        time_str = prev_dt.strftime("%I:%M %p").lstrip("0")
        weekday = prev_dt.strftime("%A")
        
        confirmation_patterns = [
            rf"{weekday}\s+at\s+{time_str}",
            rf"{time_str}\s+(?:works|is fine|is good|is perfect)",
            rf"{weekday}\s+(?:works|is fine|is good|is perfect)",
            r"(?:confirmed|all set|works perfectly)"
        ]
        
        for pattern in confirmation_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return prev_time
            
        return current_time 