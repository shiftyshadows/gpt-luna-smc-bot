#!/usr/bin/env python3

import pandas as pd
from threading import Lock

class FullDepthOrderBook:
    """
    A thread-safe implementation of a Limit Order Book (LOB) designed for 
    high-frequency cTrader Depth of Market (DOM) streams.

    This class maintains the state of bids and asks, calculates institutional 
    metrics like Weighted Average Price (WAP) and Imbalance, and identifies 
    liquidity 'walls' for SMC-based trading strategies.
    """

    def __init__(self):
        """Initializes an empty order book with thread-safe locking."""
        self.bids = {}  # id -> (price, size)
        self.asks = {}
        self.lock = Lock()

    def apply_update(self, new_quotes, deleted_ids):
        """
        Processes incremental updates from the cTrader 2155 stream.

        Args:
            new_quotes (list): List of dicts containing 'id', 'bid'/'ask', and 'size'.
            deleted_ids (list): List of quote IDs to be removed from the book.
        """
        with self.lock:
            # Add or update quotes
            for q in new_quotes:
                qid = q["id"]
                if "bid" in q:
                    # cTrader prices are sent as integers; dividing by 100,000 
                    # aligns it with standard XAUUSD decimal pricing.
                    self.bids[qid] = (q["bid"] / 100000, q["size"])
                elif "ask" in q:
                    self.asks[qid] = (q["ask"] / 100000, q["size"])

            # Remove deleted quotes
            for qid in deleted_ids:
                self.bids.pop(qid, None)
                self.asks.pop(qid, None)

    def get_full_depth(self):
        """
        Returns the entire bid and ask side of the book, sorted by price.

        Returns:
            tuple: (sorted_bids, sorted_asks) where bids are descending 
                   and asks are ascending.
        """
        with self.lock:
            bid_book = sorted(self.bids.values(), key=lambda x: x[0], reverse=True)
            ask_book = sorted(self.asks.values(), key=lambda x: x[0])
        return bid_book, ask_book

    def get_top_n(self, depth=5):
        """
        Extracts the top N levels of liquidity from both sides of the book.

        Args:
            depth (int): The number of price levels to return.

        Returns:
            tuple: (top_n_bids, top_n_asks)
        """
        bids, asks = self.get_full_depth()
        return bids[:depth], asks[:depth]

    def get_top_of_book(self):
        """Return best bid, best ask, and total quote count."""
        with self.lock:
            best_bid = max((price for price, _ in self.bids.values()), default=None)
            best_ask = min((price for price, _ in self.asks.values()), default=None)
            level_count = len(self.bids) + len(self.asks)
        return best_bid, best_ask, level_count

    def get_imbalance(self, depth=5):
        """
        Calculates the Volume Imbalance at the top of the book. 
        Filters out deep-book symmetric liquidity to detect immediate pressure.

        Args:
            depth (int): Number of price levels to include in the calculation.

        Returns:
            float: Imbalance value between -1.0 (Sell Heavy) and 1.0 (Buy Heavy).
        """
        top_bids, top_asks = self.get_top_n(depth)

        bid_vol = sum(size for _, size in top_bids)
        ask_vol = sum(size for _, size in top_asks)

        total_vol = bid_vol + ask_vol
        if total_vol == 0:
            return 0.0

        return (bid_vol - ask_vol) / (total_vol + 1e-9)

    def detect_walls(self, multiplier=3.0):
        """
        Identifies 'Liquidity Walls' where a single order is significantly larger 
        than the average order size in the book.

        Args:
            multiplier (float): The factor by which an order must exceed the average.


            tuple: (bid_walls, ask_walls)
        """
        with self.lock:
            all_bids = list(self.bids.values())
            all_asks = list(self.asks.values())

        if not all_bids or not all_asks:
            return [], []

        avg_bid = sum(q[1] for q in all_bids) / len(all_bids)
        avg_ask = sum(q[1] for q in all_asks) / len(all_asks)

        bid_walls = [q for q in all_bids if q[1] >= (avg_bid * multiplier)]
        ask_walls = [q for q in all_asks if q[1] >= (avg_ask * multiplier)]

        return bid_walls, ask_walls

    def liquidity_gaps(self):
        """
        Detects price 'holes' in the order book where liquidity is thin. 
        Large gaps often lead to slippage during market orders.

        Returns:
            tuple: (bid_gaps, ask_gaps) in price units.
        """
        with self.lock:
            bid_prices = sorted(set(p for p, _ in self.bids.values()), reverse=True)
            ask_prices = sorted(set(p for p, _ in self.asks.values()))

        bid_gaps = [bid_prices[i] - bid_prices[i + 1] for i in range(len(bid_prices) - 1)]
        ask_gaps = [ask_prices[i + 1] - ask_prices[i] for i in range(len(ask_prices) - 1)]
        return bid_gaps, ask_gaps

    def weighted_avg(self, levels):
        """
        Calculates the Volume Weighted Average Price (WAP) for a given set of levels.

        Args:
            levels (list): A list of (price, size) tuples.

        Returns:
            float: The WAP for the provided levels.
        """
        total_volume = sum(size for _, size in levels)
        if total_volume <= 0:
            return None
        return sum(price * size for price, size in levels) / total_volume

    def snapshot_metrics(self, depth=5, min_depth_threshold=1000):
        """
        Generates a comprehensive market snapshot for the Sentry/Trade Logic.

        Includes spread, Top-N imbalance, WAPs, and a 'hollow market' detection 
        flag used to predict 'Blow Through' events in SMC trading.

        Args:
            depth (int): Depth to use for WAP and Imbalance calculations.
            min_depth_threshold (int): Minimum volume required to consider signal VALID.

        Returns:
            dict: Snapshot of market metrics or None if book is insufficient.
        """
        top_bids, top_asks = self.get_top_n(depth)

        if not top_bids or not top_asks:
            return None

        best_bid = top_bids[0][0]
        best_ask = top_asks[0][0]
        spread = best_ask - best_bid

        bid_vol = sum(size for _, size in top_bids)
        ask_vol = sum(size for _, size in top_asks)

        # Calculate Top-N Imbalance (preventing the 0.0 global sum bug)
        imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol + 1e-6)

        # WAP Logic
        wap_bid = self.weighted_avg(top_bids)
        wap_ask = self.weighted_avg(top_asks)

        # Hollow Market Detection: If WAP is significantly far from Best Price, 
        # liquidity is thin and price is likely to sweep through the zone.
        # Threshold: 0.15 for Gold (~1.5 pips)
        hollow_ask = (abs(wap_ask - best_ask) > 0.15) if wap_ask else False
        hollow_bid = (abs(wap_bid - best_bid) > 0.15) if wap_bid else False

        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "imbalance": imbalance,
            "wap_bid": wap_bid,
            "wap_ask": wap_ask,
            "cumulative_depth": bid_vol + ask_vol,
            "depth_levels": len(top_bids) + len(top_asks),
            "hollow_ask": hollow_ask,
            "hollow_bid": hollow_bid,
            "signal": "VALID" if (bid_vol + ask_vol > min_depth_threshold) else "SHALLOW"
        }

    def dump_book(self):
        """
        Exports the entire book into a Pandas DataFrame for debugging or logging.

        Returns:
            pd.DataFrame: A DataFrame containing price, size, and side.
        """
        with self.lock:
            bid_data = list(self.bids.values())
            ask_data = list(self.asks.values())

        bid_df = pd.DataFrame(bid_data, columns=["price", "size"])
        ask_df = pd.DataFrame(ask_data, columns=["price", "size"])
        bid_df["side"] = "bid"
        ask_df["side"] = "ask"

        return pd.concat([bid_df, ask_df]).sort_values(by="price", ascending=False)
