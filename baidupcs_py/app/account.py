from typing import Optional, List, Dict, Union, NamedTuple
from os import PathLike
from pathlib import Path
import pickle

from baidupcs_py.baidupcs import BaiduPCSApi, PcsUser

DEFAULT_DATA_PATH = Path("~/.baidupcs-py/accounts.pk").expanduser()


class Account(NamedTuple):
    user: PcsUser

    def pcsapi(self) -> BaiduPCSApi:
        auth = self.user.auth
        assert auth, f"{self}.user.auth is None"
        return BaiduPCSApi(
            bduss=auth.bduss,
            stoken=auth.stoken,
            ptoken=auth.ptoken,
            cookies=auth.cookies,
            user_id=self.user.user_id,
        )

    @staticmethod
    def from_bduss(bduss: str, cookies: Dict[str, Optional[str]] = {}) -> "Account":
        api = BaiduPCSApi(bduss=bduss, cookies=cookies)
        user = api.user_info()
        return Account(user=user)


class AccountManager:
    """Account Manager

    Manage all accounts
    """

    def __init__(self, data_path: Optional[PathLike] = None):
        self._accounts: Dict[int, Account] = {}  # user_id (int) -> Account
        self._who: Optional[int] = None  # user_id (int)
        self._data_path = data_path

    @staticmethod
    def load_data(data_path: PathLike) -> "AccountManager":
        try:
            return pickle.load(open(data_path, "rb"))
        except Exception:
            return AccountManager(data_path=data_path)

    @property
    def accounts(self) -> List[Account]:
        return list(self._accounts.values())

    def who(self, user_id: Optional[int] = None) -> Optional[Account]:
        """Return recent `Account`"""

        user_id = user_id or self._who
        if user_id:
            return self._accounts.get(user_id)
        else:
            return None

    def su(self, user_id: int):
        """Change recent user with `PcsUser.user_id`

        Args:
            who (int): `PcsUser.user_id`
        """

        self._who = user_id

    def useradd(self, user: PcsUser):
        """Add an user to data"""
        self._accounts[user.user_id] = Account(user=user)

    def userdel(self, user_id: int):
        """Delete a user

        Args:
            who (int): `PcsUser.user_id`
        """
        if user_id in self._accounts:
            del self._accounts[user_id]
        if user_id == self._who:
            self._who = None

    def save(self, data_path: Optional[PathLike] = None):
        data_path = data_path or self._data_path
        assert data_path

        data_path = Path(data_path)
        if not data_path.parent.exists():
            data_path.parent.mkdir(parents=True)

        pickle.dump(self, open(data_path, "wb"))
