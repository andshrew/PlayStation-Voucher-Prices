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
import sys
import base64
import cv2
import numpy
import pytesseract
import requests
from bs4 import BeautifulSoup
import AndshrewDiscord as discord

def check_psn_vouchers(webhook_url="", webhook_error_url=""):

    # The Discord webhook URLs can be passed directly to this function
    if webhook_url.startswith('https://'):
        if not webhook_error_url.startswith('https://'):
            print('[check_psn_vouchers] webhook_url and webhook_error_url must both be passed'
                  ' to this function')
            return False

    # Or they can be loaded from a file 'config.json'
    if not webhook_url.startswith('https://'):
        try:
            with open('config.json', encoding="utf-8") as c:
                config_data = json.load(c)
                webhook_url = config_data['webhook_url']
                webhook_error_url = config_data['webhook_error_url']
        except OSError as ex:
            print(f'[check_psn_vouchers] Error accessing config.json: {ex.strerror}')
            return False

    # Check the Discord webhook URLs have been found
    if not webhook_url.startswith('https://') or not webhook_error_url.startswith('https://'):
        webhook_url = "disabled"
        webhook_error_url = "disabled"
        print('[check_psn_vouchers] Discord webhook variables are not set or are incorrect.'
               ' Check both webhook_url and webhook_error_url have been passed to this function,'
               ' or that they exist in config.json')
        print('[check_psn_vouchers] Discord notifications will be disabled')

    # Load product data from a file 'data.json'
    try:
        with open('data.json', encoding="utf-8") as f:
            product_data = json.load(f)
    except OSError as ex:
        print(f'[check_psn_vouchers] Error accessing data.json: {ex.strerror}')
        return False

    changed_data = False

    # Itterate through every product that has been loaded from 'data.json'
    # and retrieve the current pricing information
    for product in product_data:
        # Perform some pre-flight error processing before beginning...
        # This product has been disabled, either intentionally or
        # through too many errors, so it will be skipped
        if product["error"] == -1:
            continue

        # The error counter for this product has reached the limit
        if product["error"] >= 12:
            # It should be disabled for future runs
            product["error"] = -1
            # And a Discord notification should be sent
            discord_message_embed = {
                'title': f'{product["name"]} Error Limit 😨',
                'description': f'"{product["name"]}" (id: {product["id"]}) has reached the'
                                ' error limit. Check URLs etc.',
                'color': 10038562
            }
            discord_message = {
                'embeds': [ discord_message_embed ]
            }
            print(f'[check_psn_vouchers] error limit reached for product for id {product["id"]}:'
                   ' it will remain disabled until the error count is manually reset')
            discord.send_discord_message(message=discord_message, webhook_url=webhook_error_url)
            continue

        # There are a number of instances that will be considered failures in the following steps
        # To simplify the error handling the program assumes that an error is going to occur and
        # so the error counter is incremented now.
        # If the request and processing is successful then this will be reset to 0
        product["error"] += 1

        # Make a request to the products URL
        try:
            req = requests.get(product["url"])
        except requests.exceptions.RequestException as ex:
            print(f'[check_psn_vouchers] requests protocol error for id {product["id"]}: {ex.args}')
            continue
        except Exception as ex:
            print(f'[check_psn_vouchers] error making request for id {product["id"]}: {ex.args}')
            continue

        if not req.status_code // 100 == 2:
            print(f'[check_psn_vouchers] requests non-200 HTTP response for id {product["id"]}:'
                   ' {req.status_code}')
            continue

        # Parse the content in the response to this request to find the information that
        # we're interested in capturing
        soup = BeautifulSoup(req.content, 'html.parser')

        # Get the product name
        for item in soup.find_all("span", "item_brand_name", limit=1):
            if item.next.next.text:
                productName = item.next.next.text.strip()

        # Get the base price
        for item in soup.find_all("div", "itemcard_order_button_cross_price_wrapper cross_price",
                                  limit=1):
            if item.text:
                basePrice = float(item.text.replace('£',''))

        # Get the actual price (an image delivered as a base64 encoded string)
        for item in soup.find_all("div", "itemcard_order_button_cust_price_wrapper base_price",
                                  limit=1):
            img_src = item.find('img')['src']
            if img_src.startswith('data:image/png;base64,'):
                img_encoded = img_src.replace('data:image/png;base64,', '')

        # Decode the image from the base64 string
        img_decoded = base64.b64decode(img_encoded)

        # While pytesseract can process this image directly we can use CV2 to do some additional
        # processing on the image which will make it more suitable for OCR (ie. increase accuracy)
        img_numpy = numpy.frombuffer(img_decoded, dtype=numpy.uint8)
        img = cv2.imdecode(img_numpy, cv2.IMREAD_COLOR)

        # The processing applied here is based on this stackoverflow answer:
        # https://stackoverflow.com/a/58032585
        img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # The Otsu method will automatically find best threshold value
        _, binary_image = cv2.threshold(img_gray, 0, 255, cv2.THRESH_OTSU)

        # Invert the image if the text is white and background is black
        count_white = numpy.sum(binary_image > 0)
        count_black = numpy.sum(binary_image == 0)
        if count_black > count_white:
            binary_image = 255 - binary_image

        # Add padding to the image
        final_image = cv2.copyMakeBorder(img, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        img = final_image

        # OCR the image with pytesseract
        # A character whitelist can be used to potentially increase the accuracy
        custom_oem_psm_config = r'-c tessedit_char_whitelist=£.0123456789 --psm 7'
        try:
            price = pytesseract.image_to_string(img, config=custom_oem_psm_config)
        except Exception as ex:
            print(f'[check_psn_vouchers] pytesseract error for id {product["id"]}: {ex.args}')
            continue

        # Check if the price has been found
        # If it has changed from before then send a Discord message and update the product data
        if price:
            price = price.strip()
            try: 
                price = float(price.replace('£',''))
            except Exception as ex:
                print(f'[check_psn_vouchers] Unable to convert price to float for id {product["id"]}')
                continue

            # Additional customer loyality discount (%)
            loyalty_discount = 2

            # Reset the error counter for this product
            product["error"] = 0

            discord_message_embed = {
                'title': f'{product["name"]}',
                'url': f'{product["url"]}'
            }

            if product["price"] == -1:
                # New product (existing price is -1)
                changed_data = True
                print(f'A new challenger! {product["name"]} has been added at £{price:0.2f}')
                product["saving"] = (product["rrp"] - price) / product["rrp"] * 100
                product["savingGold"] = (product["rrp"] - (price * (100 - loyalty_discount) / 100)) / product["rrp"] * 100
                discord_message_embed["description"] = f'🎉 A new challenger has appeared!\n\nIt\'s been listed at £{price:0.2f}\n\nThat\'s a {product["saving"]:0.1f}% saving on RRP ({product["savingGold"]:0.1f}% with 🥇)'
                discord_message_embed["color"] = 15844367
                product["price"] = price
            elif price < product["price"]:
                # Yay cheaper
                changed_data = True
                print(f'Yaaay! {product["name"]} was £{product["price"]:0.2f} now £{price:0.2f}')
                product["saving"] = (product["rrp"] - price) / product["rrp"] * 100
                product["savingGold"] = (product["rrp"] - (price * (100 - loyalty_discount) / 100)) / product["rrp"] * 100
                discord_message_embed["description"] = f'✅ Yaaay, price drop!\n\nWas £{product["price"]:0.2f} now £{price:0.2f}\n\nThat\'s a {product["saving"]:0.1f}% saving on RRP ({product["savingGold"]:0.1f}% with 🥇)'
                discord_message_embed["color"] = 3066993
                product["price"] = price
            elif price > product["price"]:
                # Boo more expensive
                changed_data = True
                print(f'Boooo! {product["name"]} was £{product["price"]:0.2f} now £{price:0.2f}')
                product["saving"] = (product["rrp"] - price) / product["rrp"] * 100
                product["savingGold"] = (product["rrp"] - (price * (100 - loyalty_discount) / 100)) / product["rrp"] * 100
                discord_message_embed["description"] = f'❌ Boooo, price increase!\n\nWas £{product["price"]:0.2f} now £{price:0.2f}\n\nThat\'s still a {product["saving"]:0.1f}% saving on RRP ({product["savingGold"]:0.1f}% with 🥇)'
                discord_message_embed["color"] = 10038562
                product["price"] = price
            else:
                # Meh no change
                discord_message_embed = None
                print(f'{product["name"]} price unchanged (£{product["price"]:0.2f} now £{price:0.2f})')

            if discord_message_embed:
                discord_message = {
                    #'content': "Hello there",
                    'embeds': [ discord_message_embed ]
                }
                discord.send_discord_message(message=discord_message, webhook_url=webhook_url)

    # If any of the product data has changed calculate what the new best value product is, and
    # send a Discord message. Display the top 5 vouchers (exclude any with errors or invalid price)
    if changed_data:
        best_value = sorted(product_data, key=lambda d: d["saving"], reverse=True)[:5]
        best_value_list = list(filter(lambda d: d["error"] == 0 and d["price"] >= 0, best_value))
        if len(best_value_list) > 1:
            best_value_message = '**Current Best Value Vouchers**'
        else:
            best_value_message = '**Current Best Value Voucher**'

        for item in best_value_list:
            best_value_message += '\n'
            best_value_message += f'[{item["name"]}]({item["url"]})\t{item["saving"]:0.1f}% (or {item["savingGold"]:0.1f}% with 🥇)'

        discord_message_embed = None
        discord_message = None

        discord_message_embed = {
            'description': best_value_message,
            'color': 10181046
        }

        discord_message = {
            'embeds': [ discord_message_embed ]
        }
        discord.send_discord_message(message=discord_message, webhook_url=webhook_url)

    # Save the product data back to the file 'data.json'
    try:
        with open('data.json', "w", encoding="utf-8") as f:
            json.dump(product_data, f, indent=4)
    except OSError as ex:
        print(f'[check_psn_vouchers] Error saving data.json: {ex.strerror}')
        return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('https://github.com/andshrew/PlayStation-Voucher-Prices')
        print('')
        print('Usage:')
        print('python app.py check_psn_vouchers')
        print('python app.py send_discord_queue')
    else:
        for a in sys.argv:
            if a == "check_psn_vouchers":
                check_psn_vouchers()
                sys.exit()
            if a == "send_discord_queue":
                discord.send_discord_queue()
                sys.exit()
