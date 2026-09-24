#!/usr/bin/env python3

import asyncio
import i3ipc.aio as i3ipc
import signal
import sys
import argparse
import os
import xcffib
from xcffib.xproto import (
    MapState, Time, CW, EventMask,
    CreateNotifyEvent, UnmapNotifyEvent, DestroyNotifyEvent,
)

BIND_FOCUS = "MOVE" # "NONE" - do nothing, "MOVE" - to the center of the window affected by the binding
BIND_MOVE = "MOVE" # "NONE" - do nothing, "FOCUS" - focus window under mouse, "MOVE" - to the center of the window affected by the binding
BIND_MODE_TOGGLE = "MOVE" # "NONE" - do nothing, "MOVE" - center cursor to the center of the window affected by the binding

is_running = True
xcb_connection = None
scheduled_focus_task = None
main_loop_task = None
x_event_task = None
x_event_connection = None
override_redirect_windows = set()


def find_client_window(window):
    try:
        attrs = xcb_connection.core.GetWindowAttributes(window).reply()
        if attrs.map_state == MapState.Viewable and not attrs.override_redirect:
            return window
    except:
        pass
    try:
        tree = xcb_connection.core.QueryTree(window).reply()
        if tree and tree.children:
            for child in tree.children:
                result = find_client_window(child)
                if result is not None:
                    return result
    except:
        pass
    return None


def get_window_under_mouse():
    try:
        root = xcb_connection.get_setup().roots[0].root
        pointer = xcb_connection.core.QueryPointer(root).reply()
        if pointer and pointer.child:
            return pointer.child
    except:
        pass
    return None


def _focus_window_under_mouse_sync():
    child = get_window_under_mouse()
    if child is None:
        return
    try:
        attrs = xcb_connection.core.GetWindowAttributes(child).reply()
        if attrs is None:
            return
        if attrs.override_redirect:
            client = find_client_window(child)
            if client is not None:
                child = client
                attrs = xcb_connection.core.GetWindowAttributes(child).reply()
                if attrs is None:
                    return
        if attrs.map_state != MapState.Viewable:
            return
        xcb_connection.core.SetInputFocus(2, child, Time.CurrentTime)
        xcb_connection.flush()
    except:
        pass


async def focus_window_under_mouse():
    await asyncio.to_thread(_focus_window_under_mouse_sync)


def get_window_geometry(window):
    try:
        geom = xcb_connection.core.GetGeometry(window).reply()
        if geom is None:
            return None
        root = xcb_connection.get_setup().roots[0].root
        trans = xcb_connection.core.TranslateCoordinates(window, root, 0, 0).reply()
        if trans is None:
            return None
        return (trans.dst_x, trans.dst_y, geom.width, geom.height)
    except:
        return None


def get_window_center(window):
    geo = get_window_geometry(window)
    if geo is None:
        return None
    x, y, w, h = geo
    return (x + w // 2, y + h // 2)


def _find_deepest_viewable(window, x, y):
    try:
        tree = xcb_connection.core.QueryTree(window).reply()
        if tree and tree.children:
            for child in reversed(tree.children):
                deepest = _find_deepest_viewable(child, x, y)
                if deepest is not None:
                    return deepest
        attrs = xcb_connection.core.GetWindowAttributes(window).reply()
        if attrs is None or attrs.map_state != MapState.Viewable or attrs.override_redirect:
            return None
        geo = get_window_geometry(window)
        if geo is None:
            return None
        wx, wy, ww, wh = geo
        if wx <= x < wx + ww and wy <= y < wy + wh:
            return window
    except:
        pass
    return None


def get_topmost_window_at_point(x, y):
    root = xcb_connection.get_setup().roots[0].root
    try:
        tree = xcb_connection.core.QueryTree(root).reply()
        if tree and tree.children:
            for child in reversed(tree.children):
                deepest = _find_deepest_viewable(child, x, y)
                if deepest is not None:
                    return deepest
    except:
        pass
    return None


def move_cursor_to_point(x, y):
    root = xcb_connection.get_setup().roots[0].root
    xcb_connection.core.WarpPointer(0, root, 0, 0, 0, 0, int(x), int(y))
    xcb_connection.flush()


def move_cursor_to_topmost_at_point(cx, cy):
    current = get_topmost_window_at_point(cx, cy)
    if current is None:
        move_cursor_to_point(cx, cy)
        return
    while True:
        center = get_window_center(current)
        if center is None or center == (cx, cy):
            break
        cx, cy = center
        next_win = get_topmost_window_at_point(cx, cy)
        if next_win is None or next_win == current:
            break
        current = next_win
    center_final = get_window_center(current)
    if center_final is not None:
        move_cursor_to_point(*center_final)


async def adjust_cursor_after_focus(i3_connection):
    try:
        tree = await i3_connection.get_tree()
        focused = tree.find_focused()
        if focused is None or focused.rect is None:
            return
        rect = focused.rect
        cx = rect.x + rect.width // 2
        cy = rect.y + rect.height // 2
        await asyncio.to_thread(move_cursor_to_topmost_at_point, cx, cy)
        await schedule_focus(0.0)
    except:
        pass


async def schedule_focus(delay):
    global scheduled_focus_task
    if scheduled_focus_task is not None and not scheduled_focus_task.done():
        scheduled_focus_task.cancel()
        try:
            await scheduled_focus_task
        except asyncio.CancelledError:
            pass
    if delay == 0.0:
        await focus_window_under_mouse()
    else:
        async def delayed():
            await asyncio.sleep(delay)
            await focus_window_under_mouse()
        scheduled_focus_task = asyncio.create_task(delayed())


async def refresh_focus(*_args):
    await schedule_focus(0.0)
    asyncio.create_task(schedule_focus(0.1))


async def on_i3_binding(i3_connection, event):
    parts = event.binding.command.strip().split()
    if len(parts) < 2:
        return
    first, second = parts[0], parts[1]
    directions = ("left", "right", "up", "down")
    if first == "move" and second in directions:
        if BIND_MOVE == "MOVE":
            asyncio.create_task(adjust_cursor_after_focus(i3_connection))
        elif BIND_MOVE == "FOCUS":
            asyncio.create_task(refresh_focus())
    elif first == "focus" and second in directions:
        if BIND_FOCUS == "MOVE":
            asyncio.create_task(adjust_cursor_after_focus(i3_connection))
    elif first == "focus" and second == "mode_toggle":
        if BIND_MODE_TOGGLE == "MOVE":
            asyncio.create_task(adjust_cursor_after_focus(i3_connection))
    elif first == "layout":
        asyncio.create_task(refresh_focus())


def _subscribe_window(window):
    try:
        x_event_connection.core.ChangeWindowAttributes(
            window, CW.EventMask, [EventMask.SubstructureNotify]
        )
    except:
        pass


def _scan_tree_recursive(window, depth=0):
    if depth > 32:
        return
    try:
        attrs = x_event_connection.core.GetWindowAttributes(window).reply()
        if attrs is not None and attrs.override_redirect:
            override_redirect_windows.add(window)
    except:
        pass
    _subscribe_window(window)
    try:
        tree = x_event_connection.core.QueryTree(window).reply()
        if tree and tree.children:
            for child in tree.children:
                _scan_tree_recursive(child, depth + 1)
    except:
        pass


def handle_x_event(event):
    if isinstance(event, CreateNotifyEvent):
        if event.override_redirect:
            override_redirect_windows.add(event.window)
        _subscribe_window(event.window)
        try:
            tree = x_event_connection.core.QueryTree(event.window).reply()
            if tree and tree.children:
                for child in tree.children:
                    _scan_tree_recursive(child, 1)
        except:
            pass
        try:
            x_event_connection.flush()
        except:
            pass
    elif isinstance(event, (UnmapNotifyEvent, DestroyNotifyEvent)):
        if event.window in override_redirect_windows:
            override_redirect_windows.discard(event.window)
            if isinstance(event, UnmapNotifyEvent) and is_running:
                asyncio.create_task(refresh_focus())


async def listen_x_events():
    global x_event_connection
    try:
        x_event_connection = xcffib.connect()
    except Exception:
        return
    try:
        _scan_tree_recursive(x_event_connection.get_setup().roots[0].root)
        try:
            x_event_connection.flush()
        except:
            pass
        while is_running:
            try:
                event = x_event_connection.poll_for_event()
            except Exception:
                await asyncio.sleep(0.1)
                continue
            if event is None:
                await asyncio.sleep(0.05)
                continue
            handle_x_event(event)
    finally:
        try:
            x_event_connection.disconnect()
        except Exception:
            pass
        x_event_connection = None


async def run_i3_event_loop():
    global main_loop_task
    while is_running:
        try:
            i3_connection = await i3ipc.Connection().connect()
            i3_connection.on("binding", on_i3_binding)
            i3_connection.on("workspace::focus", refresh_focus)
            i3_connection.on("window::new", refresh_focus)
            i3_connection.on("window::close", refresh_focus)
            i3_connection.on("window::floating", refresh_focus)
            i3_connection.on("window::resize", refresh_focus)
            i3_connection.on("window::fullscreen_mode", refresh_focus)

            await refresh_focus()

            main_loop_task = asyncio.create_task(i3_connection.main())
            await main_loop_task
        except (EOFError, ConnectionError, BrokenPipeError):
            pass
        except asyncio.CancelledError:
            break
        except Exception:
            pass
        if is_running:
            await asyncio.sleep(1.0)


async def main():
    global xcb_connection, is_running, x_event_task

    parser = argparse.ArgumentParser()
    parser.add_argument("--nice", type=int, help="nice value to set")
    parser.add_argument("--realtime", type=int, help="set SCHED_RR priority (1-99)")
    args = parser.parse_args()

    if args.nice is not None:
        try:
            os.nice(args.nice)
        except:
            pass
    if args.realtime is not None:
        if not 1 <= args.realtime <= 99:
            print("Error: realtime priority must be between 1 and 99", file=sys.stderr)
            sys.exit(1)
        try:
            os.sched_setscheduler(0, os.SCHED_RR, os.sched_param(args.realtime))
        except Exception as e:
            print(f"Warning: failed to set SCHED_RR: {e}", file=sys.stderr)

    try:
        xcb_connection = xcffib.connect()
    except Exception as e:
        print(f"Fatal: cannot open X display: {e}", file=sys.stderr)
        sys.exit(1)

    loop = asyncio.get_running_loop()

    def shutdown():
        global is_running
        if not is_running:
            return
        is_running = False
        for task in (main_loop_task, scheduled_focus_task, x_event_task):
            if task is not None and not task.done():
                task.cancel()

    loop.add_signal_handler(signal.SIGINT, shutdown)
    loop.add_signal_handler(signal.SIGTERM, shutdown)

    x_event_task = asyncio.create_task(listen_x_events())

    await run_i3_event_loop()

    for task in (scheduled_focus_task, x_event_task):
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    if xcb_connection is not None:
        try:
            xcb_connection.disconnect()
        except:
            pass


if __name__ == "__main__":
    asyncio.run(main())
