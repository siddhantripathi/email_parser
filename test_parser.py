import asyncio
from parser import EmailParser
from database import Database, JSONEncoder
import json

async def test_parsing():
    try:
        test_emails =  """From: john@example.com
To: meeting@company.com
Subject: Team Meeting Planning
I'd like to schedule a team meeting for next week

        From: sarah@example.com
To: meeting@company.com
Subject: Re: Team Meeting Planning
Could you share the agenda first

        From: john@example.com
To: meeting@company.com
Subject: Re: Team Meeting Planning
Here's the agenda: Project updates and Q2 planning."""
        # Initialize parser
        parser = EmailParser()
        
        # Split emails
        emails = [e.strip() for e in test_emails.split("From: ") if e.strip()]
        emails = ["From: " + e for e in emails]
        
        # Parse emails
        parsed_data = [parser.parse_email(email) for email in emails]
        
        # Connect to MongoDB
        await Database.connect_db()
        
        # Save to MongoDB
        saved_data = await Database.save_responses(parsed_data)
        
        # Print results
        print("\nParsed and saved emails:")
        print(json.dumps(saved_data, indent=2, cls=JSONEncoder))

    except Exception as e:
        print(f"Error during execution: {e}")
        raise
    finally:
        # Always close the database connection
        await Database.close_db()

if __name__ == "__main__":
    asyncio.run(test_parsing()) 