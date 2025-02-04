import asyncio
from database import Database

async def verify_mongodb():
    try:
        # Try to connect
        connected = await Database.connect_db()
        if not connected:
            print("Failed to connect to MongoDB")
            return

        # Try to insert a test document
        test_doc = {
            "test": True,
            "message": "MongoDB connection test"
        }
        
        result = await Database.save_responses([test_doc])
        
        if result["status"] == "success":
            print("Successfully inserted test document")
            print("Database is working correctly!")
        else:
            print("Failed to insert test document")
            print(f"Error: {result.get('message')}")

    except Exception as e:
        print(f"Error during verification: {e}")
    finally:
        await Database.close_db()

if __name__ == "__main__":
    asyncio.run(verify_mongodb()) 