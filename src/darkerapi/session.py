"""One signed-in game account, and everything you can make it do.

Every method here is one call to::

    POST /api/v1/sessions/{account_key}/actions/{name}

so they are all thin by design — the method exists to give the action a Python
name, a signature and a docstring. If an action is missing, or the API has
gained one since this release, :meth:`Session.action` calls it by name.

Actions are grouped the way the API documents them::

    s = api.session("main")

    s.state()                      # session & character
    s.inventory.stash()            # inventory & stash
    s.merchants.list()             # merchants
    s.market.list(item_id="Ruby")  # marketplace
    s.trade.channels()             # trading
    s.party.list()                 # party
    s.dungeon.enter()              # dungeons

**Most actions need the account to be in the lobby.** After
``api.sessions.create(...)`` poll :meth:`state` until it reads ``in_lobby``;
:meth:`state` is the one action that works in every state.
"""

from __future__ import annotations

from typing import Any

from ._transport import Transport


class Session:
    """A handle for one connected game account.

    Get one from :meth:`darkerapi.DarkerAPI.session`. Creating it does not talk
    to the server.
    """

    def __init__(self, transport: Transport, account_key: str):
        self._t = transport
        self.account_key = account_key
        self.inventory = _Inventory(self)
        self.merchants = _Merchants(self)
        self.trade = _Trade(self)
        self.party = _Party(self)
        self.dungeon = _Dungeon(self)
        self.market = _Market(self)

    def __repr__(self) -> str:
        return f"Session({self.account_key!r})"

    # -- the call every action goes through ----------------------------------

    def action(self, name: str, **args: Any) -> Any:
        """Call any action by its API name. Costs 2 credits.

        The escape hatch: use it for anything this library does not wrap.
        Argument names are the API's own (camelCase)::

            s.action("createCharacter", nickName="Grimsby",
                     characterClass="Fighter", gender=0)

        ``api.docs()["actions"]["available"]`` lists them all.
        """
        return self._t.post(
            f"/sessions/{self.account_key}/actions/{name}",
            {k: v for k, v in args.items() if v is not None},
        )

    # -- session & character -------------------------------------------------

    def state(self) -> dict:
        """Everything known about this session: state, identity, counters, speed.

        The one action that works before the game login has finished, which
        makes it the thing to poll after opening a session. It touches no
        network of its own, so polling costs the game nothing.

        ``state`` reads ``connecting``, ``steam_auth``, ``logging_in``,
        ``in_lobby``, ``in_game`` or ``disconnected``.
        """
        return self.action("state")

    def characters(self) -> dict:
        """Every character on this account."""
        return self.action("chars")

    def character_classes(self) -> dict:
        """The classes a new character can be."""
        return self.action("characterClasses")

    def create_character(self, nick_name: str, character_class: str, gender: int) -> dict:
        """Create a character.

        :param nick_name: Letters and digits only — the game rejects spaces and
            punctuation.
        :param gender: ``0`` or ``1``.
        """
        return self.action(
            "createCharacter",
            nickName=nick_name,
            characterClass=character_class,
            gender=gender,
        )

    def delete_character(self, character_id: str) -> dict:
        """Delete a character. Not reversible."""
        return self.action("deleteCharacter", characterId=character_id)

    def character_select(self) -> dict:
        """Go back to the character-select screen."""
        return self.action("characterSelect")

    def enter(self, character_id: str) -> dict:
        """Enter the lobby as this character. Most actions need this first."""
        return self.action("enter", characterId=character_id)

    def lobby(self) -> dict:
        """The lobby's own view of the current character."""
        return self.action("lobby")

    def character_class(self) -> dict:
        """The current character's class details.

        Wraps the action named ``class``, which is a Python keyword.
        """
        return self.action("class")

    def quests(self) -> dict:
        """Quest progress."""
        return self.action("quests")

    def gold(self) -> dict:
        """Gold on the character and in storage."""
        return self.action("gold")

    def packets(self, *, after: int | None = None, limit: int | None = None) -> dict:
        """Recent raw game packets, for debugging. Paid plans only."""
        return self.action("packets", after=after, limit=limit)


class _Actions:
    """Base for the grouped namespaces. Holds no state but the session."""

    def __init__(self, session: Session):
        self._s = session

    def _call(self, name: str, **args: Any) -> Any:
        return self._s.action(name, **args)


class _Inventory(_Actions):
    """``s.inventory`` — the character's bags and the shared stash.

    Slots are addressed by ``(inventory_id, slot)``. :meth:`storages` lists the
    inventory ids available on this account.
    """

    def carried(self) -> dict:
        """What the character is carrying and wearing."""
        return self._call("inventory")

    def stash(self, *, inventory_id: int | None = None, premium: bool = False) -> dict:
        """The shared stash. Omit ``inventory_id`` for the default tab."""
        return self._call("stash", inventoryId=inventory_id, premium=premium)

    def storages(self) -> dict:
        """Every storage tab, with its id, size and whether it is unlocked."""
        return self._call("storages")

    def expand_storage(self, inventory_id: int) -> dict:
        """Buy another stash tab. Costs gold in game."""
        return self._call("expandStorage", inventoryId=inventory_id)

    def move(self, uid: str, src_inv: int, src_slot: int, dst_inv: int, dst_slot: int) -> dict:
        """Move one item to an empty slot."""
        return self._call(
            "move", uid=uid, src_inv=src_inv, src_slot=src_slot, dst_inv=dst_inv, dst_slot=dst_slot
        )

    def swap(
        self, src_uid: str, dst_uid: str, src_inv: int, src_slot: int, dst_inv: int, dst_slot: int
    ) -> dict:
        """Exchange two items' places."""
        return self._call(
            "swap",
            src_uid=src_uid,
            dst_uid=dst_uid,
            src_inv=src_inv,
            src_slot=src_slot,
            dst_inv=dst_inv,
            dst_slot=dst_slot,
        )

    def merge(
        self, src_uid: str, dst_uid: str, src_inv: int, src_slot: int, dst_inv: int, dst_slot: int
    ) -> dict:
        """Stack one pile of items onto another of the same kind."""
        return self._call(
            "merge",
            src_uid=src_uid,
            dst_uid=dst_uid,
            src_inv=src_inv,
            src_slot=src_slot,
            dst_inv=dst_inv,
            dst_slot=dst_slot,
        )

    def split_merge(
        self,
        src_uid: str,
        dst_uid: str,
        src_inv: int,
        src_slot: int,
        dst_inv: int,
        dst_slot: int,
        count: int,
    ) -> dict:
        """Move part of a stack onto another."""
        return self._call(
            "splitMerge",
            src_uid=src_uid,
            dst_uid=dst_uid,
            src_inv=src_inv,
            src_slot=src_slot,
            dst_inv=dst_inv,
            dst_slot=dst_slot,
            count=count,
        )

    def move_all(self, src_inv: int, dst_inv: int, *, premium: bool = False) -> dict:
        """Move everything from one inventory to another."""
        return self._call("moveAll", srcInv=src_inv, dstInv=dst_inv, premium=premium)

    def gather(self, src_invs: list[int], dst_inv: int, *, premium: bool = False) -> dict:
        """Pull everything from several inventories into one."""
        return self._call("gather", srcInvs=src_invs, dstInv=dst_inv, premium=premium)

    def sort_stash(
        self,
        *,
        sort_order: str | None = None,
        inventory_id: int | None = None,
        extra_inventories: list[int] | None = None,
        auto_extras: bool | None = None,
        dry_run: bool = False,
        premium: bool = False,
    ) -> dict:
        """Tidy the stash.

        :param dry_run: Report the moves it would make without making them —
            worth doing first, since a sort is a lot of item movement.
        """
        return self._call(
            "sortStash",
            sortOrder=sort_order,
            inventoryId=inventory_id,
            extraInventories=extra_inventories,
            autoExtras=auto_extras,
            dry_run=dry_run,
            premium=premium,
        )


class _Merchants(_Actions):
    """``s.merchants`` — buying from and selling to the in-game vendors."""

    def list(self) -> dict:
        """Every merchant and their id."""
        return self._call("merchants")

    def stock(self, merchant_id: str) -> dict:
        """What one merchant currently has for sale."""
        return self._call("merchantStock", merchant_id=merchant_id)

    def buy(self, stock_uid: str, merchant_id: str, *, count: int | None = None) -> dict:
        """Buy an item from a merchant's stock."""
        return self._call("merchantBuy", stockUid=stock_uid, merchant_id=merchant_id, count=count)

    def sellable(self) -> dict:
        """What you are carrying that a merchant will take, and for how much."""
        return self._call("sellable")

    def sell(self, item_uids: list[str], merchant_id: str) -> dict:
        """Sell items to a merchant."""
        return self._call("sell", itemUids=item_uids, merchant_id=merchant_id)

    def buyback(self) -> dict:
        """What you have just sold and could still buy back."""
        return self._call("buyback")


class _Trade(_Actions):
    """``s.trade`` — the trading channels, and one-to-one trades.

    Two halves that are easy to confuse: the ``channel`` methods are the public
    chat rooms where people advertise, and the ``trading_*`` methods are an
    actual open trade window with one person.
    """

    def channels(self) -> dict:
        """The trading channels you can join."""
        return self._call("tradeChannels")

    def current(self) -> dict:
        """The channel you are in, and who is in it."""
        return self._call("trade")

    def select_channel(self, index: int) -> dict:
        """Join a trading channel by its index."""
        return self._call("tradeSelect", index=index)

    def exit_channel(self) -> dict:
        """Leave the trading channel."""
        return self._call("tradeExit")

    def say(self, text: str) -> dict:
        """Say something in the channel."""
        return self._call("tradeSay", text=text)

    def whisper(self, nickname: str, text: str) -> dict:
        """Message one player directly."""
        return self._call("whisper", nickname=nickname, text=text)

    def request(self, account_id: str, *, character_id: str | None = None) -> dict:
        """Ask a player to trade."""
        return self._call("tradeRequest", accountId=account_id, characterId=character_id)

    def answer(self, account_id: str, accept: bool) -> dict:
        """Accept or refuse an incoming trade request."""
        return self._call("tradeAnswer", accountId=account_id, accept=accept)

    def dismiss(self) -> dict:
        """Clear a pending trade request."""
        return self._call("tradeDismiss")

    def tradables(self) -> dict:
        """What you could put into the open trade."""
        return self._call("tradables")

    def offer_item(self, unique_id: str, update_flag: int, *, slot_id: int | None = None) -> dict:
        """Put an item into — or take it out of — the open trade window.

        :param update_flag: What to do with it; the game's own flag.
        """
        return self._call("tradingItem", uniqueId=unique_id, updateFlag=update_flag, slotId=slot_id)

    def ready(self, is_ready: bool) -> dict:
        """Mark yourself ready. Both sides must be ready before confirming."""
        return self._call("tradingReady", isReady=is_ready)

    def confirm(self, is_ready: bool) -> dict:
        """Confirm the trade. This is the step that actually exchanges items."""
        return self._call("tradingConfirm", isReady=is_ready)

    def close(self) -> dict:
        """Close the trade window."""
        return self._call("tradingClose")

    def chat(self, text: str) -> dict:
        """Say something inside the open trade window."""
        return self._call("tradingChat", text=text)


class _Party(_Actions):
    """``s.party`` — grouping up before a dungeon."""

    def list(self) -> dict:
        """Your party and its members."""
        return self._call("party")

    def find(self, nickname: str) -> dict:
        """Look a player up by name, to get the id ``invite`` needs."""
        return self._call("partyFind", nickname=nickname)

    def invite(
        self, account_id: str, *, character_id: str | None = None, name: str | None = None
    ) -> dict:
        """Invite a player to the party."""
        return self._call("partyInvite", accountId=account_id, characterId=character_id, name=name)

    def answer(self, account_id: str, accept: bool) -> dict:
        """Accept or refuse an invitation."""
        return self._call("partyAnswer", accountId=account_id, accept=accept)

    def ready(self, is_ready: bool) -> dict:
        """Mark yourself ready to go in."""
        return self._call("partyReady", isReady=is_ready)

    def leave(self) -> dict:
        """Leave the party."""
        return self._call("partyLeave")


class _Dungeon(_Actions):
    """``s.dungeon`` — going into a raid, and getting out of a stuck one.

    If :meth:`Session.state` reports ``reconnectPending``, the account is stuck
    in a dungeon: :meth:`enter` rejoins it, :meth:`abandon` gives it up and loses
    whatever the character was carrying.
    """

    def select_region(self, region: int) -> dict:
        """Choose a server region."""
        return self._call("selectRegion", region=region)

    def select(
        self,
        dungeon_id_tag: str,
        *,
        game_type: int | None = None,
        gear_pool_index: int | None = None,
    ) -> dict:
        """Choose a dungeon and difficulty, without entering yet."""
        return self._call(
            "selectDungeon",
            dungeonIdTag=dungeon_id_tag,
            gameType=game_type,
            gearPoolIndex=gear_pool_index,
        )

    def enter(
        self,
        *,
        dungeon_id_tag: str | None = None,
        region: int | None = None,
        game_type: int | None = None,
        gear_pool_index: int | None = None,
        is_random: bool | None = None,
    ) -> dict:
        """Go in. Call with no arguments to rejoin a dungeon you are stuck in."""
        return self._call(
            "enterDungeon",
            dungeonIdTag=dungeon_id_tag,
            region=region,
            gameType=game_type,
            gearPoolIndex=gear_pool_index,
            isRandom=is_random,
        )

    def abandon(self) -> dict:
        """Give up a run in progress. The character loses what it carried."""
        return self._call("abandonGame")


class _Market(_Actions):
    """``s.market`` — the player marketplace.

    :meth:`enter` first: the marketplace is a place the character stands in, and
    the other actions need to be there.
    """

    def enter(self, *, force: bool = False) -> dict:
        """Walk the character into the marketplace."""
        return self._call("marketEnter", force=force)

    def list(
        self,
        *,
        item_id: str | None = None,
        rarity: str | None = None,
        slot: str | None = None,
        type: str | None = None,
        character_class: str | None = None,
        page: int | None = None,
        sort_type: int | None = None,
        sort_method: int | None = None,
        filter_infos: list[dict] | None = None,
    ) -> dict:
        """Search other players' listings."""
        return self._call(
            "marketList",
            itemId=item_id,
            rarity=rarity,
            slot=slot,
            type=type,
            characterClass=character_class,
            page=page,
            sortType=sort_type,
            sortMethod=sort_method,
            filterInfos=filter_infos,
        )

    def mine(self, *, per_page: int | None = None) -> dict:
        """Your own listings, sold and unsold."""
        return self._call("myMarketList", perPage=per_page)

    def buy(self, listing_id: str, price: int) -> dict:
        """Buy a listing.

        ``price`` is checked against the listing, so a stale price fails rather
        than overpaying.
        """
        return self._call("marketBuy", listingId=listing_id, price=price)

    def register(
        self, uid: str, price: int, *, count: int | None = None, contents: int | None = None
    ) -> dict:
        """List one of your items for sale."""
        return self._call("marketRegister", uid=uid, price=price, count=count, contents=contents)

    def cancel(self, listing_id: str) -> dict:
        """Take one of your listings down."""
        return self._call("marketCancel", listingId=listing_id)

    def relist(self, listing_id: str, price: int) -> dict:
        """Put an expired listing back up at a new price."""
        return self._call("marketRelistListing", listingId=listing_id, price=price)

    def transfer(self, listing_id: str) -> dict:
        """Take a sold listing's gold, or an expired listing's item, back."""
        return self._call("marketTransfer", listingId=listing_id)

    def claim_all(self) -> dict:
        """Collect everything waiting for you — gold and returned items."""
        return self._call("marketClaimAll")

    def sell_to_merchant(self, listing_id: str) -> dict:
        """Sell an expired listing to a merchant instead of relisting it."""
        return self._call("marketSellMerchant", listingId=listing_id)

    def price_check(self, tag: str, *, rarity: str | None = None, label: str | None = None) -> dict:
        """What one item is going for."""
        return self._call("priceCheck", tag=tag, rarity=rarity, label=label)

    def price_check_all(self) -> dict:
        """Price every item you are carrying."""
        return self._call("priceCheckAll")

    def price_history(self) -> dict:
        """Prices this server has recorded over time."""
        return self._call("priceHistory")

    def best_price(self, tag: str, *, rarity: str | None = None, count: int | None = None) -> dict:
        """The cheapest current listings for an item."""
        return self._call("bestPrice", tag=tag, rarity=rarity, count=count)

    def snapshot(self) -> dict:
        """The marketplace state as this session last saw it."""
        return self._call("market")
