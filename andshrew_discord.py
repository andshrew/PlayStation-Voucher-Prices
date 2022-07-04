#   MIT License

#   Copyright (c) 2022 andshrew
#   https://github.com/andshrew/PlayStation-Voucher-Prices

#   Permission is hereby granted, free of charge, to any person obtaining a copy
#   of this software and associated documentation files (the "Software"), to deal
#   in the Software without restriction, including without limitation the rights
#   to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#   copies of the Software, and to permit persons to whom the Software is
#   furnished to do so, subject to the following conditions:

#   The above copyright notice and this permission notice shall be included in all
#   copies or substantial portions of the Software.

#   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#   IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#   FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#   AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#   LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#   OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#   SOFTWARE.

import json
import requests
import datetime
import random
import pathlib

discord_queue_path='discord'

def send_discord_message(message, webhook_url, queue_message=False):

    if webhook_url == "disabled":
        return True
    try:
        message_json = json.dumps(message)
        result = requests.post(webhook_url, data=message_json, headers= {"Content-Type": "application/json; charset=utf-8"})

    except TypeError as e:
        print(f'[send_discord_message] error: {e.args}')
    except requests.exceptions.RequestException as e:
        print(f'[send_discord_message] requests protocol error: {e.args}')

    if not result.status_code // 100 == 2:
        print(f'[send_discord_message] requests HTTP error: {result.status_code}')
        if not queue_message:
            save_discord_message(message=message, webhook_url=webhook_url)
        return False
    return True

def save_discord_message(message, webhook_url):
    # This message has failed to send so try and save it to the Discord message queue
    try:
        discord_filename = pathlib.Path(discord_queue_path).joinpath(f'{datetime.datetime.utcnow().strftime("%Y-%m-%dT%H.%M.%f%Z")}-{random.randint(1000,50000)}-vouchers.json')
        pathlib.Path(discord_queue_path).mkdir(parents=True, exist_ok=True)

        # Add a timestamp to the message embed
        for e in message["embeds"]:
            e["timestamp"] = f'{datetime.datetime.utcnow().isoformat()}'
        
        # Save the webhook_url in the message (this must be removed before trying to send the message again)
        message["webhook_url"] = webhook_url

        # Save the message to a file in JSON format
        with open(discord_filename, "w") as f:
            json.dump(message, f, indent=4)
    except Exception as e:
        print(f'[send_discord_message] Error saving Discord message to queue: {e.args}')

def send_discord_queue():
    # Process all *.json files in the discord_queue_path and attempt to send them to the
    # webhook_url which has been saved within them
    try:
        files = list(pathlib.Path(discord_queue_path).glob('*.json'))
    except:
        pass

    for file in files:
        with open(file.absolute()) as f:
            message = json.load(f)
        
        webhook_url = message["webhook_url"]
        # Remove the webhook_url from the object
        message.pop("webhook_url", None)
        if send_discord_message(message=message, webhook_url=webhook_url, queue_message=True):
            try:
                file.unlink()
            except Exception as e:
                print(f'[send_discord_queue] Unable to delete {file.absolute()}: {e.args}')

if __name__ == "__main__":
    print('https://github.com/andshrew/PlayStation-Voucher-Prices')