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

import datetime
import random
import pathlib
import json
import requests

DISCORD_QUEUE_PATH='discord'

def send_discord_message(message, webhook_url, queue_message=False):

    if webhook_url == "disabled":
        return True
    try:
        message_json = json.dumps(message)
        result = requests.post(webhook_url, data=message_json,
                               headers={"Content-Type": "application/json; charset=utf-8"})

    except TypeError as ex:
        print(f'[send_discord_message] error: {ex.args}')
    except requests.exceptions.RequestException as ex:
        print(f'[send_discord_message] requests protocol error: {ex.args}')

    if not result.status_code // 100 == 2:
        print(f'[send_discord_message] requests HTTP error: {result.status_code}')
        if not queue_message:
            save_discord_message(message=message, webhook_url=webhook_url)
        return False
    return True

def save_discord_message(message, webhook_url):
    # This message has failed to send so try and save it to the Discord message queue
    try:
        discord_filename = pathlib.Path(DISCORD_QUEUE_PATH).joinpath(f'{datetime.datetime.utcnow().strftime("%Y-%m-%dT%H.%M.%f%Z")}-{random.randint(1000,50000)}-vouchers.json')
        pathlib.Path(DISCORD_QUEUE_PATH).mkdir(parents=True, exist_ok=True)

        # Add a timestamp to the message embed
        for e in message["embeds"]:
            e["timestamp"] = f'{datetime.datetime.utcnow().isoformat()}'

        # Save the webhook_url in the message
        # (this must be removed before trying to send the message again)
        message["webhook_url"] = webhook_url

        # Save the message to a file in JSON format
        with open(discord_filename, "w", encoding="utf-8") as f:
            json.dump(message, f, indent=4)
    except Exception as ex:
        print(f'[send_discord_message] Error saving Discord message to queue: {ex.args}')

def send_discord_queue():
    # Process all *.json files in the DISCORD_QUEUE_PATH and attempt to send them to the
    # webhook_url which has been saved within them
    try:
        files = list(pathlib.Path(DISCORD_QUEUE_PATH).glob('*.json'))
    except Exception:
        pass

    for file in files:
        with open(file.absolute(), encoding="utf-8") as f:
            message = json.load(f)
        
        webhook_url = message["webhook_url"]
        # Remove the webhook_url from the object
        message.pop("webhook_url", None)
        if send_discord_message(message=message, webhook_url=webhook_url, queue_message=True):
            try:
                file.unlink()
            except Exception as ex:
                print(f'[send_discord_queue] Unable to delete {file.absolute()}: {ex.args}')

if __name__ == "__main__":
    print('https://github.com/andshrew/PlayStation-Voucher-Prices')
