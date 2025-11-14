import os
import chainlit as cl
import logging
from dotenv import load_dotenv
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import MessageRole

# Load environment variables
# Try to load from .env first, then sample.env if .env doesn't exist
if not load_dotenv():
    load_dotenv("sample.env")

# Disable verbose connection logs
logger = logging.getLogger("azure.core.pipeline.policies.http_logging_policy")
logger.setLevel(logging.WARNING)

AIPROJECT_CONNECTION_STRING = os.getenv("AIPROJECT_CONNECTION_STRING")
AGENT_ID = os.getenv("AGENT_ID")

# Check if environment variables are loaded
if not AIPROJECT_CONNECTION_STRING:
    raise ValueError("AIPROJECT_CONNECTION_STRING not found in environment variables. Make sure you have a .env file.")
if not AGENT_ID:
    raise ValueError("AGENT_ID not found in environment variables. Make sure you have a .env file.")

# Use the connection string directly as the endpoint
# It should be in format: https://<resource>.services.ai.azure.com/api/projects/<project>
endpoint = AIPROJECT_CONNECTION_STRING

# Create an instance of the AIProjectClient using DefaultAzureCredential
# Only endpoint and credential are required
project_client = AIProjectClient(
    endpoint=endpoint,
    credential=DefaultAzureCredential()
)


# Chainlit setup
@cl.on_chat_start
async def on_chat_start():
    # Create a thread for the agent
    if not cl.user_session.get("thread_id"):
        thread = project_client.agents.threads.create()

        cl.user_session.set("thread_id", thread.id)
        print(f"New Thread ID: {thread.id}")

@cl.on_message
async def on_message(message: cl.Message):
    thread_id = cl.user_session.get("thread_id")
    
    try:
        # Show thinking message to user
        msg = await cl.Message("thinking...", author="agent").send()

        project_client.agents.messages.create(
            thread_id=thread_id,
            role="user",
            content=message.content,
        )
        
        # Run the agent to process the message in the thread
        run = project_client.agents.runs.create_and_process(thread_id=thread_id, agent_id=AGENT_ID)
        print(f"Run finished with status: {run.status}")

        # Check if you got "Rate limit is exceeded.", then you want to increase the token limit
        if run.status == "failed":
            raise Exception(run.last_error)

        # Get all messages from the thread
        messages = project_client.agents.messages.list(thread_id=thread_id)

        # Find the assistant's response for this run
        agent_response = None
        for message in messages:
            if message.run_id == run.id and message.role == MessageRole.AGENT and message.text_messages:
                agent_response = message.text_messages[0].text.value
                break
        
        if not agent_response:
            raise Exception("No response from the agent.")

        msg.content = agent_response
        await msg.update()

    except Exception as e:
        await cl.Message(content=f"Error: {str(e)}").send()

if __name__ == "__main__":
    # Chainlit will automatically run the application
    pass