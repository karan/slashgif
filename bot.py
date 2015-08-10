# Built-in imports
import logging
import os
import time

# Third-party dependencies
# import dataset
import giphypop
import requests
import tweepy
from ttp import ttp

# Custom imports
try:
    import config
except:
    import config_example as config


# Gloabl variable init
# db = dataset.connect(config.db)
# table = db['tweets']
TWEET_LENGTH = 140
IMAGE_URL_LENGTH = 23
MAX_TWEET_TEXT_LENGTH = TWEET_LENGTH - IMAGE_URL_LENGTH - 1
DOTS = '...'
BACKOFF = 0.5 # Initial wait time before attempting to reconnect
MAX_BACKOFF = 300 # Maximum wait time between connection attempts

logging.basicConfig(filename='logger.log',
                    level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Giphy client
giphy = giphypop.Giphy(api_key=config.giphy['key'])
# Twitter client
auth = tweepy.OAuthHandler(config.twitter['key'], config.twitter['secret'])
auth.set_access_token(config.twitter['access_token'],
    config.twitter['access_token_secret'])
api = tweepy.API(auth)
# Tweet parser
parser = ttp.Parser()
# backoff time
backoff = BACKOFF


def get_gif_filename(term):
    image = [i for i in giphy.search(term, limit=1)][0]
    filename = 'images/%s.%s' % (term.replace(' ', '_'), image.type)
    logging.debug('get_gif_filename: %s--%s' % (term, filename))

    f = open(filename, 'wb')
    f.write(requests.get(image.media_url).content)
    f.close()
    return filename


def parse_tweet(tweet_text):
    result = parser.parse(tweet_text)
    tagged_users = result.users
    tagged_hashtags = result.tags
    tagged_urls = result.urls

    for user in tagged_users:
        tweet_text = tweet_text.replace('@%s' % user, '')
    for tag in tagged_hashtags:
        tweet_text = tweet_text.replace('#%s' % tag, '')
    for url in tagged_urls:
        tweet_text = tweet_text.replace('%s' % url, '')

    logging.debug('parse_tweet: %s--%s' % (tagged_users, tweet_text))
    return tagged_users, tweet_text.strip()


def generate_reply_tweet(users):
    reply = ' '.join(['@%s' % user for user in users if user != 'slashgif'])
    if len(reply) > MAX_TWEET_TEXT_LENGTH:
        reply = reply[:MAX_TWEET_TEXT_LENGTH - len(DOTS)] + DOTS

    logging.debug('generate_reply_tweet: %s' % reply)
    return reply


class StreamListener(tweepy.StreamListener):

    def on_status(self, status):
        global backoff

        backoff = BACKOFF
        # Collect logging and debugging data
        tweet_id = status.id
        tweet_text = status.text
        tweet_from = status.user.screen_name

        if tweet_from != 'slashgif':
            logging.debug('on_status: %s--%s' % (tweet_id, tweet_text))

            # Parse tweet for search term
            tagged_users, search_term = parse_tweet(tweet_text)

            # Search and save the image
            filename = get_gif_filename(search_term)
            # Generate and send the the reply tweet
            reply_tweet = generate_reply_tweet(tagged_users)
            reply_status = api.update_with_media(filename,
                reply_tweet, tweet_id)

            logging.debug('on_status_sent: %s %s' % (
                reply_status.id_str, reply_status.text))

    def on_error(self, status_code):
        global backoff
        logging.debug('on_error: %d' % status_code)

        if status_code == 420:
            backoff = backoff * 2
            logging.debug('on_error: backoff %s seconds' % backoff)
            time.sleep(backoff)
            return True


if not os.path.exists('images/'):
    os.makedirs('images/')

stream_listener = StreamListener()
stream = tweepy.Stream(auth=api.auth, listener=stream_listener)
stream.userstream(_with='user', replies='all')
