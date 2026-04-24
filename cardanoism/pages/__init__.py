from .catalyst import catalyst
from .fund import fund
from .index import index
from .contact import contact
from .test import foreach_example
from .proposals import proposal_detail_page
from .login import login_page
from .mypage import mypage
from .governance import governance_page, governance_detail_page
from .governance_treasury import governance_treasury_page
from .governance_drep import governance_drep_page
from .governance_drep_detail import governance_drep_detail_page
from .auth import (
    line_login_redirect,
    line_callback,
    line_connect_redirect,
    google_login_redirect,
    google_callback,
    twitter_login_redirect,
    twitter_callback,
    logout_page,
)
#from .catalyst import dbtest, proposal_detail_page
