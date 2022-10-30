import os
import requests
import json

from time import sleep
from datetime import datetime
from typing import AnyStr, List
from sqlalchemy import text, func

from config import Config
from project.db.model import PaymentEvent, ChainEvent, Epoch, NetworkStat, session


def get_0l_api_data(end_point_suffix: AnyStr, output_elem: AnyStr, **options) -> List:
    """
    Gets data from the 0L API.
    :param end_point_suffix: the path of the endpoint at 0lexplorer.io
    :param output_elem: the child element in the output dictionary to be returned, if applicable
    :param options: options to be passed along with API call
    :return: list of elements representing a data set
    """
    try:
        option_string = ""
        if len(options) > 0 and end_point_suffix[1:]:
            for option_key in options.keys():
                if len(option_string) > 0:
                    option_string += "&"
                option_string += f"{option_key}={options[option_key]}"

        api_url = f"https://0lexplorer.io{end_point_suffix}{option_string}"
        result = requests.get(api_url, timeout=10).json()
        if output_elem and output_elem in result:
            result = result[output_elem]
    except Exception as e:
        # TODO add proper logging + throw specific exception
        print(f"[{datetime.now()}]:{e}")
        result = []
    return result


def load_transactions_for_addr_list(addresslist: List) -> None:
    """
    Loads all the transaction for an addresslist into the db.
    :param addresslist: list of 0L addresses
    :return: no return value
    """
    # Iterate addresslist
    for address in addresslist:

        # fetch payment events
        try:
            more_to_load = True
            batch_size = 1000
            while more_to_load:

                # Get last loaded sequence. This strategy assumes that 
                # all events before the highest (last loaded) sequence
                # have been loaded successfully. 
                # TODO add a consistency check for data prior to last
                # loaded sequence!
                max_seq = session\
                    .query(func.max(PaymentEvent.seq))\
                    .filter(PaymentEvent.address == address)\
                    .scalar()
                max_seq = max_seq if max_seq else 0
                
                # Get the data from the api
                result = get_0l_api_data(
                    end_point_suffix="/api/proxy/node/events?",
                    output_elem="result",
                    address=address,
                    start=max_seq,
                    limit=batch_size)
                
                # Iterate objects and store them in the db
                for pe_obj in result:
                    pe_id = session\
                        .query(PaymentEvent.id)\
                        .filter(PaymentEvent.address == address, 
                                PaymentEvent.seq == int(pe_obj['sequence_number']))\
                        .scalar()

                    o = PaymentEvent(
                        address=address,
                        amount=float(pe_obj['data']['amount']['amount']) / 1000000,
                        currency=pe_obj['data']['amount']['currency'],
                        _metadata=pe_obj['data']['metadata'],
                        sender=pe_obj['data']['sender'],
                        recipient=pe_obj['data']['receiver'],
                        type=pe_obj['data']['type'],
                        transactionkey=pe_obj['key'],
                        seq=int(pe_obj['sequence_number']),
                        height=int(pe_obj['transaction_version'])
                        )

                    if pe_id:
                        o.id = pe_id
                        session.merge(o)
                    else:
                        session.add(o)

                session.commit()

                if len(result) < batch_size:
                    more_to_load = False

        except Exception as e:
            print(f"[{datetime.now()}]:{e}")


def load_community_wallets_transactions() -> None:
    """
    Builds the community wallet list and loads transactions.
    :return: no return value
    """
    try:
        # Load community wallets
        f = open(f'{Config.PYTHONPATH}/project/assets/wallets.json')
        data = json.load(f)
        address_list = [wallet['account'] for wallet in data['community']]
        f.close()

        # Load data
        load_transactions_for_addr_list(addresslist=address_list)

    except Exception as e:
        print(f"[{datetime.now()}]:{e}")


if __name__ == "__main__":

    # Initial sleep time to get db seeded
    initial_sleep = int(Config.INITIAL_SLEEP_SECS)
    print(f"[{datetime.now()}] Waiting {initial_sleep} secs")
    sleep(initial_sleep)

    # Determine sleepy time for every cyclus
    sleepy_time = int(Config.SLEEP_MINS)

    if Config.ENV == "development":
        ...

    while True:
        # Load community wallets data
        print(f"[{datetime.now()}] Start loading community wallet transactions.")
        load_community_wallets_transactions()

        # Sleepy time before start next cyclus
        print(f"[{datetime.now()}] End crawling. Sleep {sleepy_time} minutes.")
        sleep(sleepy_time * 60)
