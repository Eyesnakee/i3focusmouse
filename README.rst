i3focusmouse
============

A daemon for `i3 <http://i3wm.org>`_ that ensures the focus always follows the mouse cursor, making window management more intuitive.

Features
--------

- Listens to i3 events and automatically focuses the window currently under the mouse pointer.
- Handles i3 bindings for ``focus`` and ``move`` (left/right/up/down) as well as ``mode_toggle``, moving the cursor to the center of the target window.

Dependencies
------------

- Python 3.7+
- Python libraries:
  - `i3ipc` – for communication with i3 over IPC.
  - `xcffib` – for X11 operations.

Installation
------------

Install the required libraries:

.. code-block:: bash

    pip install i3ipc xcffib

Download the script:

.. code-block:: bash

    wget https://github.com/Eyesnakee/i3focusmouse/i3focusmouse.py

Make it executable:

.. code-block:: bash

    chmod +x i3focusmouse.py

Move it to a convenient location (e.g., ``~/.config/i3/``):

.. code-block:: bash

    mv i3focusmouse.py ~/.config/i3/i3focusmouse.py

Configuration in i3
-------------------

For the script to work correctly, add the following lines to your i3 configuration file (``~/.config/i3/config`` or ``~/.i3/config``):

.. code-block:: none

    focus_follows_mouse yes
    focus_on_window_activation none
    no_focus [class=".*"]

Start the daemon automatically by adding to your i3 config:

.. code-block:: none

    exec --no-startup-id /path/to/i3focusmouse.py

If you want to run with real‑time priority (recommended for smoother operation), you can use sudo and the corresponding options. Ensure you have the appropriate sudo permissions (see below).

Command‑line Arguments
----------------------

The script accepts the following options:

- ``--nice N`` – set the nice value of the process (negative values require superuser privileges).
- ``--realtime P`` – set the process to real‑time scheduling with priority ``P`` (1‑99). Requires superuser privileges.

Example (with sudo):

.. code-block:: bash

    sudo /path/to/i3focusmouse.py --nice -20 --realtime 99

To allow this without a password when launched from the i3 config, add the following line to ``/etc/sudoers`` using ``visudo``:

.. code-block:: none

    %wheel ALL=(ALL) NOPASSWD: /path/to/i3focusmouse.py

(Adjust the group and path as needed.)

Behaviour Customisation
-----------------------

The script's behaviour for binding handling can be tuned by changing the following variables at the top of the source file:

.. code-block:: python

    # BIND_FOCUS: "NONE" - do nothing, "MOVE" - move cursor to centre of the target window
    BIND_FOCUS = "MOVE"
    # BIND_MOVE: "NONE" - do nothing, "FOCUS" - focus window under mouse, "MOVE" - move cursor to centre of the target window
    BIND_MOVE = "MOVE"
    # BIND_MODE_TOGGLE: "NONE" - do nothing, "MOVE" - move cursor to centre of the target window
    BIND_MODE_TOGGLE = "MOVE"

Note
----

On very low‑end hardware, the script may exhibit noticeable delays or sluggishness.
