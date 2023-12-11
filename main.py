from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import openai
import time
import shelve

class OpenAIAssistant:
    def __init__(self, assistant_id, api_key):
        self.assistant_id = assistant_id
        openai.api_key = api_key

    def create_thread(self, prompt):
        try:
            thread = openai.beta.threads.create()
            thread_id = thread.id

            openai.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=prompt
            )

            run = openai.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=self.assistant_id,
            )
            return run.id, thread_id
        except Exception as e:
            print(f"Error creating thread: {e}")
            return None, None

    def check_status(self, run_id, thread_id):
        try:
            run = openai.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run_id,
            )
            return run.status
        except Exception as e:
            return None

    def get_response(self, thread_id):
        try:
            response = openai.beta.threads.messages.list(thread_id=thread_id)
            return response.data[0].content[0].text.value if response.data else None
        except Exception as e:
            return None

slack_token = 'SLACK_TOKEN_HERE'
xoxb_token = 'SLACK_XOXB_TOKEN_HERE'

openai.api_key = "OPENAI_API_KEY_HERE"
assistant_id = "OPENAI_ASSISTANT_ID_HERE"
assistant = OpenAIAssistant(assistant_id, openai.api_key)

# Install the Slack app and get xoxb- token in advance
app = App(token=xoxb_token)

# Thread management
def check_if_thread_exists(user_id):
    with shelve.open("threads_db") as threads_shelf:
        return threads_shelf.get(user_id, None)

def store_thread(user_id, thread_id):
    with shelve.open("threads_db", writeback=True) as threads_shelf:
        threads_shelf[user_id] = thread_id

def format_response_for_slack(response):
    # Basic Markdown adjustments
    formatted_response = response.replace("**", "*")  # Adjust bold
    formatted_response = formatted_response.replace("\n", "\n")  # Ensure line breaks are preserved
    return formatted_response

def run_assistant(thread):
    # Retrieve the Assistant
    assistant = openai.beta.assistants.retrieve(assistant_id)

    # Run the assistant
    run = openai.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant.id,
    )

    # Wait for completion
    while run.status != "completed":
        # Be nice to the API
        time.sleep(0.5)
        run = openai.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

    # Retrieve the Messages
    messages = openai.beta.threads.messages.list(thread_id=thread.id)
    new_message = messages.data[0].content[0].text.value
    print(f"Generated message: {new_message}")
    return new_message

@app.command("/hello-socket-mode")
def hello_command(ack, body):
    user_id = body["user_id"]
    ack(f"Hi, <@{user_id}>!")

@app.command("/dbt")
def ask_command(ack, body, say):
    user_id = body["user_id"]
    user_input = body["text"]

    ack(f"Received your question, <@{user_id}>! Processing it now...")

    thread_id = check_if_thread_exists(user_id)
    if thread_id is None:
        print(f"Creating new thread for user {user_id}")
        run_id, thread_id = assistant.create_thread(user_input)
        if run_id and thread_id:
            store_thread(user_id, thread_id)
        else:
            say("Sorry, I couldn't create a conversation thread.")
            return
    else:
        print(f"Retrieving existing thread for user {user_id}")
        thread = openai.beta.threads.retrieve(thread_id)

    # Add message to thread
    message = openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_input,
    )

    # Run the assistant and get the new message
    new_message = run_assistant(thread)
    if new_message:
        formatted_response = format_response_for_slack(new_message)
        say(f"<@{user_id}>: {formatted_response}")
    else:
        say("Sorry, there was an issue getting a response.")


@app.event("app_mention")
def event_test(body, say):
    user_id = body['event']["user"]
    user_input = body['event']["text"]

    say(f"Received your question, <@{user_id}>! Processing it now...")

    thread_id = check_if_thread_exists(user_id)
    if thread_id is None:
        print(f"Creating new thread for user {user_id}")
        run_id, thread_id = assistant.create_thread(user_input)
        if run_id and thread_id:
            store_thread(user_id, thread_id)
        else:
            say("Sorry, I couldn't create a conversation thread.")
            return
    else:
        print(f"Retrieving existing thread for user {user_id}")
        thread = openai.beta.threads.retrieve(thread_id)

    # Add message to thread
    message = openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_input,
    )

    # Run the assistant and get the new message
    new_message = run_assistant(thread)
    if new_message:
        formatted_response = format_response_for_slack(new_message)
        say(f"<@{user_id}>: {formatted_response}")
    else:
        say("Sorry, there was an issue getting a response.")

if __name__ == "__main__":
    SocketModeHandler(app, slack_token).start()
