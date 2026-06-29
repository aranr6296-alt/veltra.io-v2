import os
import runpy

# Read token from token.txt if environment variable is not set
# This lets KataBump users store their token in a simple text file
if not os.getenv('DISCORD_TOKEN'):
    try:
        with open('token.txt', 'r') as f:
            token = f.read().strip()
            if token and token != "PASTE_YOUR_TOKEN_HERE":
                os.environ['DISCORD_TOKEN'] = token
                print("Token loaded from token.txt")
            else:
                print("ERROR: Edit token.txt and paste your real Discord bot token inside it.")
                exit(1)
    except FileNotFoundError:
        print("ERROR: token.txt not found and DISCORD_TOKEN env var not set.")
        exit(1)

runpy.run_path("main.py", run_name="__main__")
