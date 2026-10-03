"""Drag a rectangle anywhere on the screen, then crop that patch.

The shade is a non-activating panel, so ScreenQuery stays in the menu bar.
The panel takes the drag itself. A second event tap is not used: a tap that
swallows clicks is refused under Input Monitoring, and that refusal was
closing the crop as soon as Shift+S+O opened it.
"""

from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass

log = logging.getLogger("screenquery")

MIN_POINTS = 4
_current: RegionSelector | None = None


@dataclass(frozen=True)
class ScreenGeom:
    """One display in both AppKit space (Y up) and CoreGraphics space (Y down)."""

    ax: float
    ay: float
    width: float
    height: float
    cx: float
    cy: float


def normalize_rect(x0: float, y0: float, x1: float, y1: float, min_size: float = MIN_POINTS):
    """Axis-aligned rectangle from two corners. None when the drag is only a click."""
    left, right = (x0, x1) if x0 <= x1 else (x1, x0)
    top, bottom = (y0, y1) if y0 <= y1 else (y1, y0)
    width = right - left
    height = bottom - top
    if width < min_size or height < min_size:
        return None
    return {"X": left, "Y": top, "Width": width, "Height": height}


def appkit_point_to_cg(ax: float, ay: float, screens: list[ScreenGeom]):
    """Map one AppKit global point onto CoreGraphics global points."""
    for screen in screens:
        if screen.ax <= ax <= screen.ax + screen.width and screen.ay <= ay <= screen.ay + screen.height:
            local_x = ax - screen.ax
            local_y_down = screen.height - (ay - screen.ay)
            return (screen.cx + local_x, screen.cy + local_y_down)
    return None


def cg_point_to_appkit(cx: float, cy: float, screens: list[ScreenGeom]):
    """Map one CoreGraphics global point onto AppKit global points."""
    for screen in screens:
        if screen.cx <= cx <= screen.cx + screen.width and screen.cy <= cy <= screen.cy + screen.height:
            local_x = cx - screen.cx
            local_y_up = screen.height - (cy - screen.cy)
            return (screen.ax + local_x, screen.ay + local_y_up)
    return None


def cancel_region_select() -> None:
    current = _current
    if current is not None:
        current.cancel()


def select_region(on_done) -> None:
    """Show the drag layer. on_done receives a bounds dict, None if cancelled, or an error string."""
    global _current
    cancel_region_select()
    if sys.platform != "darwin":
        on_done(None)
        return
    selector = RegionSelector(on_done)
    _current = selector
    selector.show()


class RegionSelector:
    def __init__(self, on_done) -> None:
        self._on_done = on_done
        self._finished = False
        self._window = None
        self._view = None
        self._screens: list[ScreenGeom] = []
        self._lock = threading.Lock()
        self._cg_start: tuple[float, float] | None = None
        self._cg_current: tuple[float, float] | None = None
        self._dragging = False
        self._cursor_pushed = False
        self._thread: threading.Thread | None = None
        self._loop = None
        self._tap = None

    def show(self) -> None:
        _on_main(self._show_on_main)

    def cancel(self) -> None:
        _on_main(self._cancel_on_main)

    def draw(self, view) -> None:
        from AppKit import (
            NSBezierPath,
            NSColor,
            NSFont,
            NSFontAttributeName,
            NSForegroundColorAttributeName,
            NSInsetRect,
            NSMakeRect,
            NSString,
        )

        bounds = view.bounds()
        selection = self._view_rect(view)
        shade = NSBezierPath.bezierPathWithRect_(bounds)
        if selection is not None:
            shade.appendBezierPathWithRect_(selection)
            shade.setWindingRule_(1)
        NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.28).set()
        shade.fill()
        if selection is not None:
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.22, 0.52, 0.95, 1).set()
            border = NSBezierPath.bezierPathWithRect_(selection)
            border.setLineWidth_(2.0)
            border.stroke()
        hint = NSMakeRect(max(16, (bounds.size.width - 420) / 2), bounds.size.height - 72, 420, 36)
        pill = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(hint, 12, 12)
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.91, 0.93, 0.96, 0.94).set()
        pill.fill()
        attrs = {
            NSFontAttributeName: NSFont.systemFontOfSize_(13),
            NSForegroundColorAttributeName: NSColor.colorWithCalibratedRed_green_blue_alpha_(0.12, 0.17, 0.23, 1),
        }
        NSString.stringWithString_("Drag a rectangle. Esc cancels.").drawInRect_withAttributes_(
            NSInsetRect(hint, 16, 8),
            attrs,
        )

    def _points(self):
        with self._lock:
            return self._cg_start, self._cg_current

    def _result(self):
        start, end = self._points()
        if start is None or end is None:
            return None
        rect = normalize_rect(start[0], start[1], end[0], end[1])
        if rect is not None:
            return rect
        moved = abs(start[0] - end[0]) + abs(start[1] - end[1])
        if moved < MIN_POINTS:
            return None
        return "Drag a larger rectangle around the word or the line."

    def _view_rect(self, view):
        from AppKit import NSMakeRect

        start, end = self._points()
        if not self._dragging or start is None or end is None or view.window() is None:
            return None
        a = cg_point_to_appkit(start[0], start[1], self._screens)
        b = cg_point_to_appkit(end[0], end[1], self._screens)
        if a is None or b is None:
            return None
        frame = view.window().frame()
        x0 = a[0] - frame.origin.x
        y0 = a[1] - frame.origin.y
        x1 = b[0] - frame.origin.x
        y1 = b[1] - frame.origin.y
        left, right = (x0, x1) if x0 <= x1 else (x1, x0)
        bottom, top = (y0, y1) if y0 <= y1 else (y1, y0)
        if right - left < 1 or top - bottom < 1:
            return None
        return NSMakeRect(left, bottom, right - left, top - bottom)

    def _show_on_main(self) -> None:
        if self._finished or sys.platform != "darwin":
            return
        try:
            from screenquery.hotkey_listener import set_escape_handler

            self._screens = _screen_geoms()
            set_escape_handler(self._escape)
            self._build_window()
            self._start_tap()
        except Exception:
            log.exception("Could not open the crop layer")
            self._finish("Could not start the crop tool. Try Shift+S+O again.")
            return
        log.info("Crop is waiting for a rectangle")

    def _escape(self) -> None:
        _on_main(self._cancel_on_main)

    def _build_window(self) -> None:
        from AppKit import (
            NSBackingStoreBuffered,
            NSColor,
            NSCursor,
            NSScreen,
            NSUnionRect,
            NSViewHeightSizable,
            NSViewWidthSizable,
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
            NSWindowCollectionBehaviorIgnoresCycle,
            NSWindowCollectionBehaviorStationary,
            NSWindowCollectionBehaviorTransient,
            NSWindowStyleMaskBorderless,
            NSWindowStyleMaskNonactivatingPanel,
        )

        screens = list(NSScreen.screens() or [])
        if not screens:
            raise RuntimeError("no screens")
        frame = screens[0].frame()
        for screen in screens[1:]:
            frame = NSUnionRect(frame, screen.frame())
        # Non-activating panel: it must not become the key window, or macOS
        # puts this menu-bar app in the Dock. It still receives the drag.
        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        panel = _panel_class().alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            style,
            NSBackingStoreBuffered,
            False,
        )
        panel.setOpaque_(False)
        # A fully clear pixel lets the click fall through. This faint fill
        # keeps every point on the panel, including the selection hole.
        panel.setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.05))
        panel.setHasShadow_(False)
        panel.setLevel_(1000)
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorStationary
            | NSWindowCollectionBehaviorTransient
            | NSWindowCollectionBehaviorIgnoresCycle
        )
        panel.setFloatingPanel_(True)
        panel.setBecomesKeyOnlyIfNeeded_(False)
        panel.setHidesOnDeactivate_(False)
        panel.setWorksWhenModal_(True)
        panel.setMovable_(False)
        panel.setMovableByWindowBackground_(False)
        panel.setIgnoresMouseEvents_(False)
        panel.setAcceptsMouseMovedEvents_(True)
        view = _view_class().alloc().initWithFrame_(panel.contentView().bounds())
        view.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        view.host = self
        panel.setContentView_(view)
        self._window = panel
        self._view = view
        # orderFrontRegardless, not makeKey. A key window on a normal
        # NSWindow would activate this menu-bar app and put it in the Dock.
        panel.orderFrontRegardless()
        panel.display()
        NSCursor.crosshairCursor().push()
        self._cursor_pushed = True

    def _start_tap(self) -> None:
        # Same Input Monitoring grant as Shift+S+P. Listen-only, so a refusal
        # leaves the overlay up and the panel takes the drag itself.
        self._thread = threading.Thread(target=self._run_tap, name="screenquery-crop", daemon=True)
        self._thread.start()

    def _run_tap(self) -> None:
        import Quartz
        from CoreFoundation import (
            CFMachPortCreateRunLoopSource,
            CFRunLoopAddSource,
            CFRunLoopGetCurrent,
            CFRunLoopRun,
            kCFRunLoopCommonModes,
        )

        mask = (
            Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseDown)
            | Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseDragged)
            | Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseUp)
            | Quartz.CGEventMaskBit(Quartz.kCGEventRightMouseDown)
            | Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
        )
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            mask,
            self._on_event,
            None,
        )
        if tap is None or self._finished:
            log.info("Crop is using the overlay for the drag")
            return
        source = CFMachPortCreateRunLoopSource(None, tap, 0)
        loop = CFRunLoopGetCurrent()
        self._loop = loop
        self._tap = tap
        CFRunLoopAddSource(loop, source, kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
        log.info("Crop is watching the pointer")
        CFRunLoopRun()
        if self._loop is loop:
            self._loop = None
        self._tap = None

    def _on_event(self, _proxy, event_type, event, _refcon):
        import Quartz

        try:
            if event_type in (
                getattr(Quartz, "kCGEventTapDisabledByTimeout", -1),
                getattr(Quartz, "kCGEventTapDisabledByUserInput", -2),
            ):
                tap = self._tap
                if tap is not None:
                    Quartz.CGEventTapEnable(tap, True)
                return event
            if self._finished:
                return event
            if event_type == Quartz.kCGEventKeyDown:
                keycode = int(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode))
                if keycode == 53:
                    _on_main(self._cancel_on_main)
                return event
            if event_type == Quartz.kCGEventRightMouseDown:
                _on_main(self._cancel_on_main)
                return event
            point = Quartz.CGEventGetLocation(event)
            x, y = float(point.x), float(point.y)
            if event_type == Quartz.kCGEventLeftMouseDown:
                self._begin_drag(x, y)
            elif event_type == Quartz.kCGEventLeftMouseDragged:
                self._move_drag(x, y)
            elif event_type == Quartz.kCGEventLeftMouseUp:
                self._move_drag(x, y)
                _on_main(self._mouse_up_on_main)
        except Exception:
            log.exception("Crop event failed")
        return event

    def _begin_drag(self, x: float, y: float) -> None:
        with self._lock:
            if self._finished:
                return
            if self._dragging:
                self._cg_current = (x, y)
            else:
                self._cg_start = (x, y)
                self._cg_current = (x, y)
                self._dragging = True
        _on_main(self._redraw)

    def _move_drag(self, x: float, y: float) -> None:
        with self._lock:
            if self._finished:
                return
            if not self._dragging:
                self._cg_start = (x, y)
                self._dragging = True
            self._cg_current = (x, y)
        _on_main(self._redraw)

    def _cg_from_appkit(self):
        from AppKit import NSEvent

        loc = NSEvent.mouseLocation()
        return appkit_point_to_cg(float(loc.x), float(loc.y), self._screens)

    def mouse_down(self) -> None:
        point = self._cg_from_appkit()
        if point is None:
            return
        self._begin_drag(point[0], point[1])

    def mouse_dragged(self) -> None:
        point = self._cg_from_appkit()
        if point is None:
            return
        self._move_drag(point[0], point[1])

    def mouse_up(self) -> None:
        point = self._cg_from_appkit()
        if point is not None:
            self._move_drag(point[0], point[1])
        self._mouse_up_on_main()

    def _mouse_up_on_main(self) -> None:
        if self._finished:
            return
        self._finish(self._result())

    def _cancel_on_main(self) -> None:
        if self._finished:
            return
        self._finish(None)

    def _finish(self, result) -> None:
        if self._finished:
            return
        self._finished = True
        global _current
        if _current is self:
            _current = None
        self._teardown()
        callback = self._on_done
        self._on_done = None
        if callback is not None:
            callback(result)

    def _teardown(self) -> None:
        try:
            from screenquery.hotkey_listener import set_escape_handler

            set_escape_handler(None)
        except Exception:
            log.exception("Could not release the crop cancel key")
        tap = self._tap
        if tap is not None:
            try:
                import Quartz

                Quartz.CGEventTapEnable(tap, False)
            except Exception:
                log.exception("Could not disable the crop event tap")
        loop = self._loop
        self._loop = None
        if loop is not None:
            try:
                from CoreFoundation import CFRunLoopStop

                CFRunLoopStop(loop)
            except Exception:
                log.exception("Could not stop the crop event tap")
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        if self._cursor_pushed:
            self._cursor_pushed = False
            try:
                from AppKit import NSCursor

                NSCursor.pop()
            except Exception:
                log.exception("Could not restore the cursor")
        window = self._window
        self._window = None
        view = self._view
        self._view = None
        if view is not None:
            view.host = None
        if window is not None:
            window.orderOut_(None)
            window.close()

    def _redraw(self) -> None:
        view = self._view
        if view is not None:
            view.setNeedsDisplay_(True)


def _screen_geoms() -> list[ScreenGeom]:
    import Quartz
    from AppKit import NSScreen

    geoms = []
    for screen in NSScreen.screens() or []:
        frame = screen.frame()
        number = screen.deviceDescription().objectForKey_("NSScreenNumber")
        display_id = int(number)
        bounds = Quartz.CGDisplayBounds(display_id)
        geoms.append(
            ScreenGeom(
                ax=float(frame.origin.x),
                ay=float(frame.origin.y),
                width=float(frame.size.width),
                height=float(frame.size.height),
                cx=float(bounds.origin.x),
                cy=float(bounds.origin.y),
            )
        )
    return geoms


def _on_main(fn) -> None:
    if sys.platform != "darwin":
        fn()
        return
    try:
        from Foundation import NSThread
        from PyObjCTools import AppHelper
    except Exception:
        log.exception("AppKit is not available for the crop layer")
        return
    if NSThread.isMainThread():
        try:
            fn()
        except Exception:
            log.exception("Could not update the crop layer")
        return
    AppHelper.callAfter(fn)


_View = None
_Panel = None


def _panel_class():
    global _Panel
    if _Panel is not None:
        return _Panel
    from AppKit import NSPanel

    class RegionPanel(NSPanel):
        # Key is allowed so the drag is delivered. The nonactivating style
        # keeps the menu-bar app from becoming a Dock app.
        def canBecomeKeyWindow(self):
            return True

        def canBecomeMainWindow(self):
            return False

    _Panel = RegionPanel
    return _Panel


def _view_class():
    global _View
    if _View is not None:
        return _View
    from AppKit import NSView

    class RegionView(NSView):
        def isOpaque(self):
            return False

        def acceptsFirstResponder(self):
            return True

        def acceptsFirstMouse_(self, _event):
            # The app is not active. Without this, the drag click is dropped.
            return True

        def resetCursorRects(self):
            from AppKit import NSCursor

            self.addCursorRect_cursor_(self.bounds(), NSCursor.crosshairCursor())

        def hitTest_(self, _point):
            return self

        def mouseDown_(self, _event):
            host = getattr(self, "host", None)
            if host is not None:
                host.mouse_down()

        def mouseDragged_(self, _event):
            host = getattr(self, "host", None)
            if host is not None:
                host.mouse_dragged()

        def mouseUp_(self, _event):
            host = getattr(self, "host", None)
            if host is not None:
                host.mouse_up()

        def rightMouseDown_(self, _event):
            host = getattr(self, "host", None)
            if host is not None:
                host.cancel()

        def keyDown_(self, event):
            host = getattr(self, "host", None)
            if host is not None and int(event.keyCode()) == 53:
                host.cancel()

        def drawRect_(self, _dirty):
            host = getattr(self, "host", None)
            if host is not None:
                host.draw(self)

    _View = RegionView
    return _View
