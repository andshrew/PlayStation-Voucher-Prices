#   MIT License

#   Copyright (c) 2022-2023 andshrew
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

import argparse
import base64
import cv2
import json
import logging
import logging.handlers
from pathlib import Path
import numpy
import pytesseract
import requests
import sys

from bs4 import BeautifulSoup
import AndshrewDiscord as discord

GITHUB_URL = 'https://github.com/andshrew/PlayStation-Voucher-Prices'

def init_logging(debug_mode=False, disable_log_to_file=False):
    log_format_stdout = '[%(asctime)s]%(levelname)s: %(message)s'
    log_level_stdout = logging.INFO

    if debug_mode:
        log_format_stdout = '[%(asctime)s %(filename)s->%(funcName)s():%(lineno)s]%(levelname)s: %(message)s'
        log_level_stdout = logging.DEBUG
    logging.basicConfig(format=log_format_stdout, level=log_level_stdout)
    logger = logging.getLogger()
    
    if disable_log_to_file:
        logging.debug('Logging to file is disabled')

    if not disable_log_to_file:
        log_path = Path('log')
        log_name = 'app.log'
        logging.debug(f'Creating logger file hander -> path:"{log_path}" filename:"{log_name}"')
        if log_path.exists() is False:
            try:
                log_path.mkdir()
                logging.debug(f'Created log file directory: "{log_path}"')
            except Exception as ex:
                logging.error(f'Unable to create log file directory: path:"{log_path}" ex: {ex.args}')
                logging.warning('Program will be unable to log to a file')
        
        if log_path.exists():
            log_path = log_path.joinpath(log_name)
            log_format_file = '[%(asctime)s %(filename)s->%(funcName)s():%(lineno)s]%(levelname)s: %(message)s'
            log_level_file = logging.INFO
            if debug_mode:
                log_level_file = logging.DEBUG
            log_handler_file = logging.handlers.TimedRotatingFileHandler(log_path, when='midnight', interval=1, backupCount=7)
            log_handler_file.setFormatter(logging.Formatter(log_format_file))
            log_handler_file.setLevel(log_level_file)
            logger.addHandler(log_handler_file)
    return

def check_psn_vouchers(webhook_url="", webhook_error_url=""):

    # The Discord webhook URLs can be passed directly to this function
    if webhook_url.startswith('https://'):
        if not webhook_error_url.startswith('https://'):
            logging.error('webhook_url and webhook_error_url must both be passed to this function')
            return False

    # Or they can be loaded from a file 'config.json'
    if not webhook_url.startswith('https://'):
        try:
            with open('config.json', encoding="utf-8") as c:
                config_data = json.load(c)
                webhook_url = config_data['webhook_url']
                webhook_error_url = config_data['webhook_error_url']
        except OSError as ex:
            logging.error(f'Unable to access config.json: {ex.strerror}')
            return False

    # Check the Discord webhook URLs have been found
    if not webhook_url.startswith('https://') or not webhook_error_url.startswith('https://'):
        webhook_url = "disabled"
        webhook_error_url = "disabled"
        logging.warning('Discord webhook variables are not set or are incorrect.'
               ' Check both webhook_url and webhook_error_url have been passed to this function,'
               ' or that they exist in config.json')
        logging.info('Discord notifications will be disabled')

    # Load product data from a file 'data.json'
    try:
        with open('data.json', encoding="utf-8") as f:
            product_data = json.load(f)
    except OSError as ex:
        logging.error(f'Unable to access data.json: {ex.strerror}')
        return False
    
    product_data = product_data_migration(product_data)

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
            logging.error(f'Requests protocol error for id {product["id"]}: {ex.args}')
            continue
        except Exception as ex:
            logging.error(f'Unable to request id {product["id"]}: {ex.args}')
            continue

        if not req.status_code // 100 == 2:
            logging.error(f'Requests non-200 HTTP response for id {product["id"]}:'
                   ' {req.status_code}')
            continue

        # Reset variables to prevent unintended re-use
        productName = basePrice = img_src = img_encoded = img_decoded = None

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

        # Check an image has been found
        if img_encoded == None:
            logging.error(f'No price image in response for id {product["id"]}')
            continue

        # Get price from image
        price_base = parse_base64_image_price(img_base64=img_encoded, transparent=True)

        if price_base == None:
            logging.error(f'Unable to OCR price image in response for id {product["id"]}')
            continue

        # Get the member price (an image delivered as a base64 encoded string)
        img_src = img_encoded = price_member = None

        try:
            for item in soup.find("div", class_="membership_infowrapper").find("div", id="gold").find_all("div", class_="reward_value",
                                limit=1):
                img_src = item.find('img')['src']
                if img_src.startswith('data:image/png;base64,'):
                    img_encoded = img_src.replace('data:image/png;base64,', '')
        except Exception as ex:
            logging.error(f'Member price not in expected location for id {product["id"]}')
            continue

        # Check an image has been found
        if img_encoded == None:
            logging.error(f'No member price image in response for id {product["id"]}')
            continue

        # Get member price from image
        price_member = parse_base64_image_price(img_base64=img_encoded, transparent=True)

        if price_member == None:
            logging.error(f'Unable to OCR member price image in response for id {product["id"]}')
            continue

        # Check if the price has changed from before then send a Discord message and update the product data

        # Additional customer loyality discount (%)
        loyalty_discount = 2

        # Reset the error counter for this product
        product["error"] = 0

        discord_message_embed = {
            'title': f'{product["name"]}',
            'url': f'{product["url"]}'
        }

        current_product = product.copy()
        current_product["price"] = price_base
        current_product["priceGold"] = price_member
        current_product["saving"] = (current_product["rrp"] - price_base) / product["rrp"] * 100
        current_product["savingGold"] = (current_product["rrp"] - price_member) / product["rrp"] * 100

        if current_product == product:
            # No Change
            discord_message_embed = None
            logging.info(f'{product["name"]} price unchanged (£{product["price"]:0.2f} now £{price_base:0.2f}, member price £{product["priceGold"]:0.2f} now £{price_member:0.2f})')

        if current_product != product:
            # Change
            changed_data = True
            if product["price"] == -1:
                # New product (existing price is -1)
                logging.info(f'A new challenger! {product["name"]} has been added at £{price_base:0.2f}. Member price £{price_member:0.2f}')
                discord_message_embed["description"] = f'🎉 A new challenger has appeared!\n\nIt\'s been listed at £{price_base:0.2f}\n\nMember price £{product["priceGold"]:0.2f}\n\nThat\'s a {current_product["saving"]:0.1f}% saving on RRP ({current_product["savingGold"]:0.1f}% with 🥇)'
                discord_message_embed["color"] = 15844367
            elif price_base < product["price"] or price_member < product["priceGold"]:
                # Yay cheaper
                logging.info(f'Yaaay! {product["name"]} was £{product["price"]:0.2f} now £{price_base:0.2f}. Member price was £{product["priceGold"]:0.2f} now £{price_member:0.2f}.')
                discord_message_embed["description"] = f'✅ Yaaay, price drop!\n\nWas £{product["price"]:0.2f} now £{price_base:0.2f}\n\nMember price £{product["priceGold"]:0.2f} now £{price_member:0.2f}\n\nThat\'s a {current_product["saving"]:0.1f}% saving on RRP ({current_product["savingGold"]:0.1f}% with 🥇)'
                discord_message_embed["color"] = 3066993
            elif price_base > product["price"] or price_member > product["priceGold"]:
                # Boo more expensive
                logging.info(f'Boooo! {product["name"]} was £{product["price"]:0.2f} now £{price_base:0.2f}. Member price was £{product["priceGold"]:0.2f} now £{price_member:0.2f}.')
                discord_message_embed["description"] = f'❌ Boooo, price increase!\n\nWas £{product["price"]:0.2f} now £{price_base:0.2f}\n\nMember price £{product["priceGold"]:0.2f} now £{price_member:0.2f}\n\nThat\'s still a {current_product["saving"]:0.1f}% saving on RRP ({current_product["savingGold"]:0.1f}% with 🥇)'
                discord_message_embed["color"] = 10038562
            
            product["price"] = current_product["price"]
            product["priceGold"] = current_product["priceGold"]
            product["saving"] = current_product["saving"]
            product["savingGold"] = current_product["savingGold"]

        if discord_message_embed:
            discord_message = {
                #'content': "Hello there",
                'embeds': [ discord_message_embed ]
            }
            discord.send_discord_message(message=discord_message, webhook_url=webhook_url)

    # If any of the product data has changed calculate what the new best value product is, and
    # send a Discord message. Display the top 5 vouchers (exclude any with errors or invalid price)
    if changed_data:
        best_value = sorted(product_data, key=lambda d: d["savingGold"], reverse=True)[:5]
        best_value_list = list(filter(lambda d: d["error"] == 0 and d["price"] >= 0, best_value))
        if len(best_value_list) > 1:
            best_value_message = '**Current Best Value Vouchers**'
        else:
            best_value_message = '**Current Best Value Voucher**'

        for item in best_value_list:
            best_value_message += '\n'
            best_value_message += f'[{item["name"]}]({item["url"]})\t{item["saving"]:0.1f}% (or {item["savingGold"]:0.1f}% with 🥇)\n£{item["price"]:0.2f} (or £{item["priceGold"]:0.2f} with gold)\n'

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

def parse_base64_image_price(img_base64, transparent=False):
    
    # Decode the image from the base64 string
    img_decoded = base64.b64decode(img_base64)

    # While pytesseract can process this image directly we can use CV2 to do some additional
    # processing on the image which will make it more suitable for OCR (ie. increase accuracy)
    img_numpy = numpy.frombuffer(img_decoded, dtype=numpy.uint8)

    if transparent:
        img = cv2.imdecode(img_numpy, cv2.IMREAD_UNCHANGED)
        if img.shape[2] != 4:
            logging.warn(f'Transparent is set but image has no alpha channel')

        # Set all RGB values to black without altering alpha (transparency) channel
        img[:,:,:3] = [0, 0, 0]

    if transparent == False:    
        img = cv2.imdecode(img_numpy, cv2.IMREAD_COLOR)

        # TODO
        # Is this actually doing anything?

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
        logging.error(f'pytesseract parsing error: {ex.args}')
        return None

    if price:
        price = price.strip()
        try: 
            price = float(price.replace('£',''))
        except Exception as ex:
            logging.error(f'Unable to convert price to float')
            return None

    return price

def product_data_migration(product_data):
    for product in product_data:
        if "priceGold" not in product:
            product["priceGold"] = product["price"]
    return product_data

if __name__ == "__main__":

    args_parser = argparse.ArgumentParser(description='PSN Voucher Price Checker', usage='python app.py --check_psn_vouchers',
                                          epilog=GITHUB_URL)
    args_parser.formatter_class = argparse.RawDescriptionHelpFormatter
    args_parser.add_argument("--check_psn_vouchers", action='store_true', help="check PSN voucher prices", default=False)
    args_parser.add_argument("--send_discord_queue", action='store_true', help="send queued Discord messages", default=False)
    args_parser.add_argument("-d", "--debug", action='store_true', help="enable debug logging", default=False)
    args_parser.add_argument("--no-log-file", action='store_true', help="disable logging to file", default=False)
    args = args_parser.parse_args()

    init_logging(args.debug, args.no_log_file)
    logging.debug('Executing with the following args...')
    logging.debug(args)

    if args.check_psn_vouchers:
        check_psn_vouchers()
        sys.exit()

    if args.send_discord_queue:
        discord.send_discord_queue()
        sys.exit()

    args_parser.print_help()
    sys.exit()