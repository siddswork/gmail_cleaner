"""
In-memory state for the FastAPI backend.

Stores:
  - gmail_services: authenticated Gmail API service objects per account
  - sync_threads: background sync threads per account
  - pending_flows: OAuth flows awaiting callback, keyed by state param
"""
import threading


# {account_email: Gmail API service object}
gmail_services: dict[str, object] = {}

# {account_email: threading.Thread}
sync_threads: dict[str, threading.Thread] = {}

# {state_param: Flow object}
pending_flows: dict[str, object] = {}
