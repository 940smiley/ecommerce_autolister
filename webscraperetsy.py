"""ETSY IMAGE SCRAPER.

Scrapes images from your list on ETSY

Author: ehgp
"""
import os
from os import listdir
from os.path import isfile, join
from pathlib import Path
from bs4 import BeautifulSoup
import re
import string
import json
import pickle
import requests
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import chromedriver_autoinstaller
import time
import random
import pandas as pd
from getpass import getuser
import logging
import logging.config
import sys
import datetime as dt
import yaml
import keyring


def format_filename(s):
    """Take a string and return a valid filename constructed from the string.

    Uses a whitelist approach: any characters not present in valid_chars are
    removed.

    Note: this method may produce invalid filenames such as ``, `.` or `..`
    When I use this method I prepend a date string like '2009_01_15_19_46_32_'
    and append a file extension like '.txt', so I avoid the potential of using
    an invalid filename.

    """
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    filename = "".join(re.sub("[^A-Za-z0-9]+", " ", c) for c in s if c in valid_chars)
    filename = " ".join(filename.split())
    return filename


def _load_config():
    """Load the configuration yaml and return dictionary of setttings.

    Returns:
        yaml as a dictionary.
    """
    config_path = os.path.dirname(os.path.realpath(__file__))
    config_path = os.path.join(config_path, "xpath_params.yaml")
    with open(config_path, "r") as config_file:
        config_defs = yaml.safe_load(config_file.read())

    if config_defs.values() is None:
        raise ValueError("parameters yaml file incomplete")

    return config_defs


# Creds
user = getuser()
etsy_email = keyring.get_password("ETSY_EMAIL", user)
etsy_pass = keyring.get_password("ETSY_PASSWORD", user)

# Paths
path = Path(os.getcwd())
# binary_path = Path(path, "chromedriver.exe")
chromedriver_autoinstaller.install()
dropship_sh_path = Path(path, "Dropshipping Items", "DROPSHIPPING_SPREADSHEET.xlsx")
dropship_path = Path(path, "Dropshipping Items")

# Logging
Path("log").mkdir(parents=True, exist_ok=True)
log_config = Path(path, "log_config.yaml")
timestamp = "{:%Y_%m_%d_%H_%M_%S}".format(dt.datetime.now())
with open(log_config, "r") as log_file:
    config_dict = yaml.safe_load(log_file.read())
    # Append date stamp to the file name
    log_filename = config_dict["handlers"]["file"]["filename"]
    base, extension = os.path.splitext(log_filename)
    base2 = "_" + os.path.splitext(os.path.basename(__file__))[0] + "_"
    log_filename = "{}{}{}{}".format(base, base2, timestamp, extension)
    config_dict["handlers"]["file"]["filename"] = log_filename
    logging.config.dictConfig(config_dict)
logger = logging.getLogger(__name__)

cf = _load_config()

DEFAULT_HEADERS = cf["GENERAL_PARAMS"]["DEFAULT_HEADERS"]

PAGES = cf["ETSY_WEBSCRAPER_PARAMS"]["PAGES"]

ETSY_LOGIN = cf["ETSY_WEBSCRAPER_PARAMS"]["ETSY_LOGIN"]

ETSY_USERNAME_XPATH = cf["ETSY_WEBSCRAPER_PARAMS"]["ETSY_USERNAME_XPATH"]

ETSY_PASSWORD_XPATH = cf["ETSY_WEBSCRAPER_PARAMS"]["ETSY_PASSWORD_XPATH"]

ETSY_LOGIN_BUTTON_XPATH = cf["ETSY_WEBSCRAPER_PARAMS"]["ETSY_LOGIN_BUTTON_XPATH"]

ETSY_SOUP_SHIPPRICE_EXT = cf["ETSY_WEBSCRAPER_PARAMS"]["ETSY_SOUP_SHIPPRICE_EXT"]

ETSY_SOUP_SHIPHOW_EXT = cf["ETSY_WEBSCRAPER_PARAMS"]["ETSY_SOUP_SHIPHOW_EXT"]

ETSY_LINK_LIST = cf["ETSY_WEBSCRAPER_PARAMS"]["ETSY_LINK_LIST"]

ETSY_SOUP_IMAGELINK_EXT = cf["ETSY_WEBSCRAPER_PARAMS"]["ETSY_SOUP_IMAGELINK_EXT"]

# Configure ChromeOptions
options = Options()
options.page_load_strategy = "eager"
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)
# prefs = {"profile.managed_default_content_settings.images": 2}
# options.add_experimental_option("prefs", prefs)
options.add_argument("user-data-dir=.profile-ETSY")
# options.add_argument('--proxy-server=https://'+ self.proxies[0])
# options.add_argument('--proxy-server=http://'+ self.proxies[0])
# options.add_argument('--proxy-server=socks5://'+ self.proxies[0])
options.add_argument("--disable-notifications")
options.add_argument("--ignore-certificate-errors")
options.add_argument("--ignore-ssl-errors")
# options.add_argument('user-agent = Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36')
# options.add_argument('--headless')
# options.add_argument('--window-size=1910x1080')
# options.add_argument('--proxy-server=http://'+ proxies[0]))
options.add_argument("--disable-infobars")  # disabling infobars
options.add_argument("--disable-extensions")  # disabling extensions
options.add_argument("--disable-gpu")  # applicable to windows os only
options.add_argument("--disable-dev-shm-usage")  # overcome limited resource problems
options.add_argument("--remote-debugging-port=9222")


def save_to_file_wishlist(response, i):
    """Save response to response.html."""
    with open(
        Path(path, "etsy responses", f"responseetsywishlist{i}.html"),
        "w",
        encoding="utf-8",
    ) as fp:
        fp.write(response)


def save_html_to_file(response, title):
    """Save response to response.html."""
    with open(
        Path(path, "etsy responses", f"responseetsy{title}.html"),
        "w",
        encoding="utf-8",
    ) as fp:
        fp.write(response)


def fix_cookies_and_load_to_requests(cookie_list, request_session):
    """Fix cookie values and add cookies to request_session."""
    for index in range(len(cookie_list)):
        for item in cookie_list[index]:
            if type(cookie_list[index][item]) != str:
                cookie_list[index][item] = str(cookie_list[index][item])
        cookies = requests.utils.cookiejar_from_dict(cookie_list[index])
        request_session.cookies.update(cookies)
    return request_session


# you function to get the cookies from the file.
def load_cookies(filename):
    """Load cookies from file."""
    with open(filename, "rb") as f:
        return pickle.load(f)


new_descriptions = []
new_titles = []
extracted_links = []
new_prices = []
new_ship_prices = []
new_ship_how = []


def listingscraper(new_items):
    """Scrape listing title, description, price, ship price."""
    for idx, link in enumerate(new_items):

        page = requests.get(link)

        save_html_to_file(page.text, idx)

        soup = BeautifulSoup(page.text, "lxml")
        json_content = soup.find_all(type="application/ld+json")
        content = json.loads(json_content[0].contents[0])
        try:
            title = (
                content["name"]
                .replace("Details about  \xa0", "")
                .replace("from China", "")
                .replace("Worldwide", "")
                .replace("Etsy", "")
                .replace("etsy", "")
                .replace("ETSY", "")
                .replace("eBay", "")
                .replace("ebay", "")
                .replace("EBAY", "")
                .replace("AliExpress", "")
                .replace("aliexpress", "")
                .replace("ALIEXPRESS", "")
                .replace("LIFETIME WARRANTY", "")
                .replace("WARRANTY", "")
                .replace("lifetime warranty", "")
                .replace("|", "")
                .replace("\n", " ")
                .replace("\xa0", "")
                .replace(" Store Categories Store Categories ", "")
                .replace("US $", "")
                .replace("Return", "")
                .replace("return", "")
                .replace("Refund", "")
                .replace("refund", "")
            )
        except Exception as e:
            print(e)
            title = ""
            pass

        new_titles.append(title)

        try:
            description = (
                content["description"]
                .replace("Details about  \xa0", "")
                .replace("from China", "")
                .replace("Worldwide", "")
                .replace("Etsy", "")
                .replace("etsy", "")
                .replace("ETSY", "")
                .replace("eBay", "")
                .replace("ebay", "")
                .replace("EBAY", "")
                .replace("AliExpress", "")
                .replace("aliexpress", "")
                .replace("ALIEXPRESS", "")
                .replace("LIFETIME WARRANTY", "")
                .replace("WARRANTY", "")
                .replace("lifetime warranty", "")
                .replace("|", "")
                .replace("\n", " ")
                .replace("\xa0", "")
                .replace(" Store Categories Store Categories ", "")
                .replace("US $", "")
                .replace("Return", "")
                .replace("return", "")
                .replace("Refund", "")
                .replace("refund", "")
            )
        # product-description > div > div.detailmodule_html > div > div > div > div > div > div > div > div > div:nth-child(4) > div
        except Exception as e:
            print(e)
            description = ""
            pass

        new_descriptions.append(description)

        try:
            price = (
                content["offers"]["highPrice"]
                .replace("Details about  \xa0", "")
                .replace("from China", "")
                .replace("Worldwide", "")
                .replace("Etsy", "")
                .replace("etsy", "")
                .replace("ETSY", "")
                .replace("eBay", "")
                .replace("ebay", "")
                .replace("EBAY", "")
                .replace("AliExpress", "")
                .replace("aliexpress", "")
                .replace("ALIEXPRESS", "")
                .replace("LIFETIME WARRANTY", "")
                .replace("WARRANTY", "")
                .replace("lifetime warranty", "")
                .replace("|", "")
                .replace("\n", " ")
                .replace("\xa0", "")
                .replace(" Store Categories Store Categories ", "")
                .replace("US $", "")
                .replace("Return", "")
                .replace("return", "")
                .replace("Refund", "")
                .replace("refund", "")
            )
        except Exception as e:
            print(e)
            price = ""
            pass

        new_prices.append(price)

        try:
            ship_price = (
                str(soup.find(ETSY_SOUP_SHIPPRICE_EXT).text)
                .replace("Details about  \xa0", "")
                .replace("from China", "")
                .replace("Worldwide", "")
                .replace("Etsy", "")
                .replace("etsy", "")
                .replace("ETSY", "")
                .replace("eBay", "")
                .replace("ebay", "")
                .replace("EBAY", "")
                .replace("AliExpress", "")
                .replace("aliexpress", "")
                .replace("ALIEXPRESS", "")
                .replace("LIFETIME WARRANTY", "")
                .replace("WARRANTY", "")
                .replace("lifetime warranty", "")
                .replace("|", "")
                .replace("\n", " ")
                .replace("\xa0", "")
                .replace(" Store Categories Store Categories ", "")
                .replace("US $", "")
                .replace("Return", "")
                .replace("return", "")
                .replace("Refund", "")
                .replace("refund", "")
            )
        except Exception as e:
            print(e)
            ship_price = ""
            pass

        new_ship_prices.append(ship_price)

        try:
            ship_how = str(soup.find(ETSY_SOUP_SHIPHOW_EXT).text)
        except Exception as e:
            print(e)
            ship_how = ""
            pass

        new_ship_how.append(ship_how)

    new_items_df = pd.DataFrame(
        {
            "new_title": new_titles,
            "new_description": new_descriptions,
            "new_link": new_items,
            "new_price": new_prices,
            "new_ship_price": new_ship_prices,
            "new_ship_how": new_ship_how,
        }
    )

    new_items_df.to_csv(Path(path, "Dropshipping Items", "new_items_etsy.csv"))


# title = 'Skateboard Complete Standard Street Cruiser 32 INCH BY 8 INCH Board'
# page = requests.get('https://www.etsy.com/listing/869334327/skateboard-complete-standard-street?')
# soup = BeautifulSoup(page.text, 'lxml')
# save_html_to_file(page,0)
# <script type="application/ld+json">


def linkscraperetsy():
    """Extract Links from ETSY list."""
    # Go to the website
    with webdriver.Chrome(
        # executable_path=binary_path,
     options=options) as driver:
        driver.get(ETSY_LOGIN)
        if os.path.exists(".profile-ETSY") is False:
            # Logging IN
            time.sleep(random.uniform(0.15, 0.4))
            username = (
                WebDriverWait(driver, 10)
                .until(EC.element_to_be_clickable((By.XPATH, ETSY_USERNAME_XPATH)))
                .send_keys(etsy_email)
            )
            username = username
            time.sleep(random.uniform(0.15, 0.4))
            password = (
                WebDriverWait(driver, 10)
                .until(EC.element_to_be_clickable((By.XPATH, ETSY_PASSWORD_XPATH)))
                .send_keys(etsy_pass)
            )
            password = password
            # time.sleep(random.randint(30,40))
            time.sleep(random.uniform(0.15, 0.4))
            login = (
                WebDriverWait(driver, 10)
                .until(EC.element_to_be_clickable((By.XPATH, ETSY_LOGIN_BUTTON_XPATH)))
                .click()
            )
            login = login
        # Save the cookies in a file
        with open(Path(path, "cookiesetsy.dat"), "wb") as f:
            pickle.dump(driver.get_cookies(), f)

    saved_cookies_list = load_cookies(str(path) + "cookiesetsy.dat")

    # Set request session
    initial_state = requests.Session()

    initial_state_with_cookies = fix_cookies_and_load_to_requests(
        cookie_list=saved_cookies_list, request_session=initial_state
    )

    for x in range(1, PAGES):
        time.sleep(random.uniform(0.15, 1.1))
        page = initial_state_with_cookies.get(f"{ETSY_LINK_LIST}{x}#")

        save_to_file_wishlist(page.text, x)

        soup = BeautifulSoup(page.text, "lxml")

        for link in soup.findAll(
            "a", attrs={"class": "display-inline-block listing-link"}
        ):
            extracted_links.append(link.get("href").split("ref")[0])

    product_list = pd.read_excel(
        Path(path, "Dropshipping Items", "DROPSHIPPING_SPREADSHEET.xlsx"),
        sheet_name="PRODUCT_LIST",
    )
    not_new_items = list(product_list["Link"])

    new_items = [link for link in extracted_links if link not in not_new_items]

    listingscraper(new_items)


def imagewebscraperetsy(URL, title):
    """Webscrape Images from ETSY."""
    page = requests.get(URL)

    save_html_to_file(page.text, title)

    soup = BeautifulSoup(page.text, "lxml")
    soup = soup

    imgfilename = re.findall(ETSY_SOUP_IMAGELINK_EXT, page.text)
    imgfilename = ["".join(i) for i in imgfilename]
    imgfilenameclean = [x for x in imgfilename if "fullxfull" in x]
    if imgfilenameclean == []:
        imgfilenameclean = [x for x in imgfilename if "75x75" in x]

    os.makedirs(Path(path, "Dropshipping Items", title), exist_ok=True)

    for idx, url in enumerate(imgfilenameclean):
        with open(
            Path(path, "Dropshipping Items", title, f"{title}{idx}.jpg"), "wb"
        ) as f:
            response = requests.get(url)
            f.write(response.content)
