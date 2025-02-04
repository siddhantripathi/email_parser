from typing import Dict, Any, Optional, List
import spacy
import re
from datetime import datetime, timedelta
import dateparser
import json
from pathlib import Path
import logging
import uuid

# Set up logging
logger = logging.getLogger(__name__)

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

    def _split_emails(self, text: str) -> list[str]:
        """Improved email splitting with encoding handling and validation"""
        # Normalize encoding first
        text = text.replace(''', "'").replace(''', "'").replace('"', '"').replace('"', '"')
        
        emails = []
        current_email = []
        email_start = False
        
        # Simpler boundary pattern that matches standard email headers
        boundary_pattern = re.compile(
            r'^From:\s*[\w\.-]+@[\w\.-]+\s*$',
            re.IGNORECASE | re.MULTILINE
        )
        
        lines = text.split('\n')
        for line in lines:
            stripped_line = line.strip()
            if boundary_pattern.match(stripped_line):
                if current_email:
                    if self._validate_email_chunk(current_email):
                        emails.append('\n'.join(current_email))
                    current_email = []
                email_start = True
            
            if email_start:
                current_email.append(line)
        
        # Add final email if valid
        if current_email and self._validate_email_chunk(current_email):
            emails.append('\n'.join(current_email))
        
        # If no valid emails found, try parsing as single email
        if not emails and self._validate_email_chunk(lines):
            emails.append(text)
        
        return emails

    def _validate_email_chunk(self, email_lines: list[str]) -> bool:
        """Validate basic email structure"""
        required_headers = {'from', 'to', 'subject'}
        found_headers = set()
        
        for line in email_lines[:10]:  # Check first 10 lines for headers
            if line.lower().startswith('from:'):
                found_headers.add('from')
            elif line.lower().startswith('to:'):
                found_headers.add('to')
            elif line.lower().startswith('subject:'):
                found_headers.add('subject')
                
        return required_headers.issubset(found_headers)

    def parse_email(self, email_text: str) -> Dict[str, Any]:
        """Parse a single email and extract relevant information"""
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
        primary_type = reply_types[0][0] if reply_types else "unknown"
        
        # Extract all information
        proposed_time = None
        if time_info.get("proposed_times"):
            proposed_time = time_info["proposed_times"][-1]
        elif time_info.get("original_time"):
            proposed_time = time_info["original_time"]
        
        meeting_link = self._extract_meeting_link(email_text)
        delegate_info = self._extract_delegate_info(doc, email_text)
        
        # Format additional notes
        notes = []
        if time_info.get("uncertainty"):
            notes.append("Schedule uncertainty indicated")
        if time_info.get("alternative_times_suggested"):
            times_str = ", ".join(time_info.get("proposed_times", []))
            notes.append(f"Alternative times suggested: {times_str}")
        if time_info.get("original_time"):
            notes.append(f"Original time was {time_info['original_time']}")
        
        return {
            "from_email": headers.get("from"),
            "to_email": headers.get("to"),
            "subject": headers.get("subject"),
            "reply_type": primary_type,
            "reply_type_scores": reply_type_scores,
            "proposed_time": proposed_time,
            "meeting_link": meeting_link,
            "delegate_to": delegate_info.get("delegate_email") if isinstance(delegate_info, dict) else delegate_info,
            "additional_info": time_info,
            "additional_notes": "\n".join(f"- {note}" for note in notes) if notes else None,
            "processed_at": datetime.utcnow().isoformat()
        }

    def _extract_headers(self, email_text: str) -> Dict[str, str]:
        """Extract email headers (From, To, Subject)"""
        headers = {
            'from': None,
            'to': None,
            'subject': None
        }
        
        lines = email_text.split('\n')
        for line in lines[:10]:  # Check first 10 lines for headers
            line = line.strip()
            if line.lower().startswith('from:'):
                headers['from'] = line[5:].strip()
            elif line.lower().startswith('to:'):
                headers['to'] = line[3:].strip()
            elif line.lower().startswith('subject:'):
                headers['subject'] = line[8:].strip()
            
            # Break if we found all headers
            if all(headers.values()):
                break
            
        return headers

    def _extract_meeting_link(self, email_text: str) -> Optional[str]:
        """Extract meeting links from email text"""
        # Common meeting link patterns
        link_patterns = [
            r'https?://[^\s<>"]+?(?:zoom|meet|teams|webex|gotomeeting)\.[^\s<>"]+',
            r'https?://[^\s<>"]+?/[^\s<>"]*?(?:join|meeting|conf)[^\s<>"]*'
        ]
        
        for pattern in link_patterns:
            match = re.search(pattern, email_text, re.IGNORECASE)
            if match:
                return match.group(0)
        
        return None

    def _extract_delegate_info(self, doc, email_text: str) -> Dict[str, Any]:
        """Extract delegation information from email"""
        delegate_info = {
            'delegate_email': None,
            'delegate_name': None,
            'confidence': 0.0
        }
        
        # Look for delegation patterns
        delegation_patterns = [
            r'(?:can|could|would)\s+(?:you|someone)\s+(?:take|handle|cover)',
            r'(?:need|looking for)\s+(?:someone|anybody|anyone)\s+to\s+(?:take|handle|cover)',
            r'(?:please|kindly)\s+(?:take|handle|cover)\s+(?:this|the|my)',
            r'(?:delegate|transfer|assign)\s+(?:to|this|the)',
        ]
        
        # Extract potential delegate email addresses
        email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
        emails = re.findall(email_pattern, email_text)
        
        # Calculate confidence based on patterns
        confidence = 0.0
        for pattern in delegation_patterns:
            if re.search(pattern, email_text, re.IGNORECASE):
                confidence += 0.25  # Increment confidence for each matching pattern
        
        # If we found delegation patterns and emails
        if confidence > 0 and emails:
            # Filter out sender and recipient emails
            headers = self._extract_headers(email_text)
            potential_delegates = [e for e in emails 
                                 if e != headers.get('from') 
                                 and e != headers.get('to')]
            
            if potential_delegates:
                delegate_info['delegate_email'] = potential_delegates[0]
                delegate_info['confidence'] = min(confidence, 1.0)
        
        return delegate_info

    def extract_time_info(self, doc, text: str) -> Dict[str, Any]:
        """Extract time-related information from email"""
        time_info = {
            "uncertainty": False,
            "alternative_times_suggested": False,
            "original_time": None,
            "proposed_times": []
        }
        
        try:
            # Handle explicit dates with times
            date_time_pattern = r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?)\s+(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm))"
            explicit_matches = re.finditer(date_time_pattern, text, re.IGNORECASE)
            
            # Handle relative weekday mentions
            weekday_pattern = r"((?:next\s+)?(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)(?:day)?)'?s?\s+(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm))"
            weekday_matches = re.finditer(weekday_pattern, text, re.IGNORECASE)
            
            found_times = []
            today = datetime.now()
            next_year = today.year + 1
            
            # Process explicit dates
            for match in explicit_matches:
                date_str = match.group(1)
                time_str = match.group(2)
                full_str = f"{date_str} {time_str} {next_year}"
                
                parsed_time = dateparser.parse(full_str, settings={
                    'PREFER_DATES_FROM': 'future',
                    'RELATIVE_BASE': today
                })
                if parsed_time:
                    found_times.append(parsed_time)
            
            # Process weekday mentions
            weekday_map = {
                'monday': 0, 'mon': 0,
                'tuesday': 1, 'tues': 1,
                'wednesday': 2, 'wednes': 2,
                'thursday': 3, 'thurs': 3,
                'friday': 4, 'fri': 4,
                'saturday': 5, 'satur': 5,
                'sunday': 6, 'sun': 6
            }
            
            for match in weekday_matches:
                weekday_str = match.group(1).lower()
                time_str = match.group(2)
                
                for day_name, day_num in weekday_map.items():
                    if day_name in weekday_str:
                        target_weekday = day_num
                        current_weekday = today.weekday()
                        
                        if 'next' in weekday_str:
                            days_ahead = target_weekday - current_weekday + 7
                        else:
                            days_ahead = target_weekday - current_weekday
                            if days_ahead <= 0:
                                days_ahead += 7
                        
                        target_date = today + timedelta(days=days_ahead)
                        full_str = f"{target_date.strftime('%Y-%m-%d')} {time_str}"
                        
                        parsed_time = dateparser.parse(full_str, settings={
                            'PREFER_DATES_FROM': 'future',
                            'RELATIVE_BASE': today
                        })
                        if parsed_time:
                            found_times.append(parsed_time)
                        break
            
            # Set times in response
            if found_times:
                time_info["original_time"] = found_times[0].isoformat()
                if len(found_times) > 1:
                    time_info["proposed_times"] = [t.isoformat() for t in found_times[1:]]
                    time_info["alternative_times_suggested"] = True
            
            # Check for uncertainty
            uncertainty_patterns = [
                r"possible", r"would it be", r"can we", r"maybe",
                r"not sure", r"if possible", r"(?:could|would) you",
                r"available", r"(?<!not )flexible"
            ]
            
            for pattern in uncertainty_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    time_info["uncertainty"] = True
                    break
                
        except Exception as e:
            print(f"Error in time extraction: {str(e)}")
        
        return time_info

    def generate_thread_id(self) -> str:
        """Generate a unique thread ID"""
        return f"thread_{uuid.uuid4().hex[:24]}"