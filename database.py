from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import json
from typing import List, Dict, Any
from bson import ObjectId
import asyncio
import re
import logging
import os

logger = logging.getLogger(__name__)

class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)

class Database:
    client = None
    db = None

    @classmethod
    async def connect_db(cls):
        """Connect to MongoDB"""
        try:
            # Get MongoDB URI from environment variable
            mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
            cls.client = AsyncIOMotorClient(mongodb_uri)
            cls.db = cls.client.email_parser
            logger.info("Connected to MongoDB")
            
            # Create indexes if needed
            await cls.create_indexes()
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    @classmethod
    async def create_indexes(cls):
        """Create necessary indexes"""
        try:
            await cls.db.responses.create_index("created_at")
            await cls.db.responses.create_index("from_email")
            await cls.db.responses.create_index("reply_type")
            await cls.db.responses.create_index("thread_id")  # New index for thread tracking
            await cls.db.responses.create_index("subject")
            logger.info("Indexes created successfully")
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")

    @classmethod
    async def verify_connection(cls):
        """Verify database connection is active"""
        try:
            if cls.client:
                await cls.client.admin.command('ping')
                return True
            return False
        except Exception:
            return False

    @classmethod
    def _normalize_subject(cls, subject: str) -> str:
        """Normalize subject by removing Re:, Fwd:, etc. and whitespace"""
        subject = re.sub(r'^(?:Re|Fwd|etc):\s*', '', subject, flags=re.IGNORECASE)
        return subject.strip().lower()

    @classmethod
    def _generate_thread_id(cls, subject: str) -> str:
        """Generate a thread ID from email subject"""
        # Remove Re:, Fwd:, etc. and clean the subject
        clean_subject = re.sub(r'^(?:Re|Fwd|FW|Forward):\s*', '', subject, flags=re.IGNORECASE)
        clean_subject = clean_subject.strip().lower()
        # Create a unique identifier based on the clean subject
        return f"thread_{ObjectId()}"

    @classmethod
    async def get_thread_id(cls, subject: str, reference_id: str = None) -> str:
        """Get existing thread ID or create new one"""
        if reference_id:
            # If reference_id is provided, use it
            return reference_id
        
        # Clean the subject
        clean_subject = re.sub(r'^(?:Re|Fwd|FW|Forward):\s*', '', subject, flags=re.IGNORECASE)
        clean_subject = clean_subject.strip().lower()
        
        # Look for existing thread with similar subject
        existing_thread = await cls.db.responses.find_one({
            "subject": {"$regex": f"^(?:Re: )?{re.escape(clean_subject)}$", "$options": "i"}
        })
        
        if existing_thread and "thread_id" in existing_thread:
            return existing_thread["thread_id"]
        
        # If no existing thread found, create new thread_id
        return cls._generate_thread_id(subject)

    @classmethod
    async def save_responses(cls, responses: List[Dict[str, Any]], thread_id: str = None) -> Dict[str, Any]:
        """Save parsed email responses to MongoDB"""
        try:
            if cls.client is None:
                await cls.connect_db()

            # Process each response
            processed_responses = []
            current_thread_id = thread_id
            
            for response in responses:
                if not current_thread_id:
                    # Get or create thread_id for this group of responses
                    current_thread_id = await cls.get_thread_id(response.get('subject', ''))
                
                # Add thread_id and timestamps to response
                response['thread_id'] = current_thread_id
                response['created_at'] = datetime.utcnow()
                response['updated_at'] = datetime.utcnow()
                processed_responses.append(response)

            # Insert all responses
            result = await cls.db.responses.insert_many(processed_responses)
            logger.info(f"Saved {len(result.inserted_ids)} documents to MongoDB")

            # Fetch and return the saved documents
            saved_docs = await cls.db.responses.find({
                '_id': {'$in': result.inserted_ids}
            }).to_list(length=None)

            # Convert ObjectIds to strings for JSON serialization
            for doc in saved_docs:
                doc['_id'] = str(doc['_id'])
                doc['thread_id'] = str(doc['thread_id'])
                if 'created_at' in doc:
                    doc['created_at'] = doc['created_at'].isoformat()

            return {
                "status": "success",
                "count": len(saved_docs),
                "thread_id": current_thread_id,
                "data": json.loads(json.dumps(saved_docs, cls=JSONEncoder))
            }

        except Exception as e:
            logger.error(f"Failed to save responses: {e}")
            raise

    @classmethod
    async def get_thread_responses(cls, thread_id: str) -> Dict[str, Any]:
        """Get all responses in a thread"""
        try:
            if cls.client is None:
                await cls.connect_db()

            cursor = cls.db.responses.find({"thread_id": thread_id}).sort("created_at", 1)
            responses = await cursor.to_list(length=None)

            # Convert ObjectIds to strings
            for response in responses:
                response['_id'] = str(response['_id'])

            return {
                "status": "success",
                "thread_id": thread_id,
                "count": len(responses),
                "data": json.loads(json.dumps(responses, cls=JSONEncoder))
            }

        except Exception as e:
            logger.error(f"Failed to get thread responses: {e}")
            raise

    @classmethod
    def _prepare_response(cls, documents: List[Dict]) -> List[Dict]:
        """Prepare documents for JSON response"""
        for doc in documents:
            doc["_id"] = str(doc["_id"])
            doc["thread_id"] = str(doc["thread_id"])
            if "created_at" in doc:
                doc["created_at"] = doc["created_at"].isoformat()
        return documents

    @classmethod
    async def get_responses(cls, limit: int = 10) -> Dict[str, Any]:
        """Get recent responses"""
        try:
            if cls.client is None:
                await cls.connect_db()

            cursor = cls.db.responses.find().sort('created_at', -1).limit(limit)
            responses = await cursor.to_list(length=None)
            
            # Convert ObjectIds to strings
            for response in responses:
                response['_id'] = str(response['_id'])

            return {
                "status": "success",
                "count": len(responses),
                "thread_id": None,
                "data": json.loads(json.dumps(responses, cls=JSONEncoder))
            }
        except Exception as e:
            logger.error(f"Failed to get responses: {e}")
            raise

    @classmethod
    async def close_db(cls):
        """Close MongoDB connection"""
        if cls.client is not None:
            cls.client.close()
            cls.client = None
            cls.db = None
            logger.info("Closed MongoDB connection")

    @classmethod
    async def verify_connection(cls):
        """Verify database connection is active"""
        try:
            if cls.client:
                await cls.client.admin.command('ping')
                return True
            return False
        except Exception:
            return False 