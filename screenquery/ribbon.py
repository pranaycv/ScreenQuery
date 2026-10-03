"""Short translucent status ribbon drawn with AppKit.

pywebview's tiny transparent window was easy to lose: it was ordered like a
normal window and could sit on a different display. This panel is borderless,
non-activating, above other windows, and pinned to the screen under the pointer.
"""

from __future__ import annotations

import logging
import sys
import threading

log = logging.getLogger("screenquery")

RIBBON_HEIGHT = 58
PATH_HEIGHT = 18
RESPONSE_LINE = 18
MAX_RESPONSE_ROWS = 10
CORNER_RADIUS = 22
_PAD_TOP = 10
_GAP = 4
_PAD_BOTTOM = 8
_FILL = (0.86, 0.93, 0.99, 0.82)


def plain_block(text: str | None) -> str:
    """Keep sentence breaks. Collapse spaces inside each line."""
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = []
    previous_blank = False
    for line in raw.split("\n"):
        cleaned = " ".join(line.split())
        if not cleaned:
            if lines and not previous_blank:
                lines.append("")
                previous_blank = True
            continue
        lines.append(cleaned)
        previous_blank = False
    return "\n".join(lines).strip()


def wrapped_rows(text: str, width: int, font_size: int = 13) -> int:
    """How many rows a wrapping label needs, capped so the ribbon stays short."""
    if not (text or "").strip():
        return 1
    columns = max(8, int(width / max(1, font_size * 0.52)))
    rows = 0
    for paragraph in text.split("\n"):
        length = len(paragraph)
        rows += 1 if length == 0 else max(1, (length + columns - 1) // columns)
    return max(1, min(MAX_RESPONSE_ROWS, rows))


def response_height(text: str, width: int) -> int:
    return max(RESPONSE_LINE, min(MAX_RESPONSE_ROWS * RESPONSE_LINE, wrapped_rows(text, width) * RESPONSE_LINE))


def panel_height(text: str, width: int) -> int:
    return _PAD_TOP + PATH_HEIGHT + _GAP + response_height(text, width) + _PAD_BOTTOM


def ribbon_lines(status) -> tuple[str, str]:
    """Save path, then the model reply. The reply may be several sentences."""
    save_error = plain_block(getattr(status, "save_error", None))
    save_display = plain_block(getattr(status, "save_display", None))
    if save_error:
        path_line = save_error.split("\n", 1)[0]
    elif save_display:
        path_line = save_display.split("\n", 1)[0]
    else:
        path_line = "Not saved"

    if getattr(status, "llm_working", False):
        response_line = "Asking OpenAI…"
    else:
        llm_error = plain_block(getattr(status, "llm_error", None))
        answer = plain_block(getattr(status, "answer", None))
        banner = plain_block(getattr(status, "banner", None))
        clipboard_error = plain_block(getattr(status, "clipboard_error", None))
        if llm_error:
            response_line = llm_error
        elif answer:
            response_line = answer
        elif banner:
            response_line = banner
        elif clipboard_error:
            response_line = clipboard_error
        else:
            response_line = ""
    return path_line, response_line


def ribbon_text(status) -> str:
    path_line, response_line = ribbon_lines(status)
    return path_line if not response_line else f"{path_line}\n{response_line}"


def ribbon_is_error(status) -> bool:
    return bool(
        getattr(status, "llm_error", None)
        or getattr(status, "banner_is_error", False)
        or getattr(status, "save_error", None)
        or getattr(status, "clipboard_error", None)
    )


class RibbonPanel:
    def __init__(self) -> None:
        self._panel = None
        self._path_label = None
        self._response_label = None
        self._target = None
        self._generation = 0
        self._timer: threading.Timer | None = None

    def show(self, status, seconds: float | None) -> None:
        path_line, response_line = ribbon_lines(status)
        error = ribbon_is_error(status)
        self._generation += 1
        generation = self._generation
        self._cancel_timer()
        if seconds is not None and seconds > 0:
            timer = threading.Timer(seconds, lambda: self._hide_if_current(generation))
            timer.daemon = True
            self._timer = timer
            timer.start()
        _on_main(lambda: self._show_on_main(path_line, response_line, error))

    def hide(self) -> None:
        self._generation += 1
        self._cancel_timer()
        _on_main(self._hide_on_main)

    def _hide_if_current(self, generation: int) -> None:
        if generation != self._generation:
            return
        _on_main(self._hide_on_main)

    def _cancel_timer(self) -> None:
        timer = self._timer
        self._timer = None
        if timer is not None:
            timer.cancel()

    def _show_on_main(self, path_line: str, response_line: str, error: bool) -> None:
        if sys.platform != "darwin":
            return
        self._ensure()
        self._apply_text(path_line, response_line, error)
        self._place()
        self._panel.setAlphaValue_(1.0)
        self._panel.orderFrontRegardless()

    def _hide_on_main(self) -> None:
        panel = self._panel
        if panel is not None:
            panel.orderOut_(None)

    def _ensure(self) -> None:
        if self._panel is not None:
            return
        from AppKit import (
            NSBackingStoreBuffered,
            NSButton,
            NSColor,
            NSMakeRect,
            NSPanel,
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
            NSWindowCollectionBehaviorStationary,
            NSWindowStyleMaskBorderless,
            NSWindowStyleMaskNonactivatingPanel,
        )

        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 800, RIBBON_HEIGHT),
            style,
            NSBackingStoreBuffered,
            False,
        )
        panel.setOpaque_(False)
        panel.setHasShadow_(True)
        # Clear window fill. The content view paints a rounded rect, so the
        # corner pixels stay transparent instead of a square plate.
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setLevel_(24)  # NSStatusWindowLevel, above normal windows
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorStationary
        )
        panel.setHidesOnDeactivate_(False)
        panel.setFloatingPanel_(True)
        panel.setBecomesKeyOnlyIfNeeded_(True)
        panel.setWorksWhenModal_(True)

        content = _ribbon_content_class().alloc().initWithFrame_(panel.contentView().frame())
        panel.setContentView_(content)
        _round_panel(content)

        path_label = _make_label(NSMakeRect(16, 30, 700, 18), 12, bold=True, wrap=False)
        response_label = _make_label(NSMakeRect(16, 8, 700, 18), 13, bold=False, wrap=True)
        content.addSubview_(path_label)
        content.addSubview_(response_label)

        target = _RibbonActions.alloc().init()
        target.panel = panel
        close = NSButton.alloc().initWithFrame_(NSMakeRect(760, 16, 28, 28))
        close.setTitle_("✕")
        close.setBezelStyle_(1)
        close.setBordered_(False)
        close.setTarget_(target)
        close.setAction_("close:")
        if hasattr(close, "setContentTintColor_"):
            close.setContentTintColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(0.12, 0.17, 0.23, 1))
        content.addSubview_(close)
        target.close_button = close

        self._panel = panel
        self._path_label = path_label
        self._response_label = response_label
        self._target = target

    def _apply_text(self, path_line: str, response_line: str, error: bool) -> None:
        from AppKit import NSColor

        if self._path_label is not None:
            self._path_label.setStringValue_(path_line or "Not saved")
        if self._response_label is None:
            return
        color = (
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.72, 0.28, 0.25, 1)
            if error
            else NSColor.colorWithCalibratedRed_green_blue_alpha_(0.12, 0.17, 0.23, 1)
        )
        self._response_label.setTextColor_(color)
        self._response_label.setStringValue_(response_line)
        self._response_text = response_line

    def _place(self) -> None:
        from AppKit import NSEvent, NSMouseInRect, NSScreen

        panel = self._panel
        if panel is None:
            return
        mouse = NSEvent.mouseLocation()
        screen = None
        for candidate in NSScreen.screens():
            if NSMouseInRect(mouse, candidate.frame(), False):
                screen = candidate
                break
        if screen is None:
            screen = NSScreen.mainScreen()
        frame = screen.visibleFrame()
        width = max(480, int(frame.size.width) - 24)
        text_width = max(120, width - 56)
        reply = getattr(self, "_response_text", "") or ""
        reply_height = response_height(reply, text_width)
        if self._response_label is not None and reply:
            reply_height = max(reply_height, _measured_height(self._response_label, reply, text_width))
            reply_height = min(MAX_RESPONSE_ROWS * RESPONSE_LINE, reply_height)
        height = _PAD_TOP + PATH_HEIGHT + _GAP + reply_height + _PAD_BOTTOM
        x = int(frame.origin.x + 12)
        y = int(frame.origin.y + frame.size.height - height - 8)
        panel.setFrame_display_(
            __import__("AppKit").NSMakeRect(x, y, width, height),
            True,
        )
        content = panel.contentView()
        if content is not None:
            _round_panel(content)
        if hasattr(panel, "invalidateShadow"):
            panel.invalidateShadow()
        path_y = _PAD_BOTTOM + reply_height + _GAP
        if self._path_label is not None:
            self._path_label.setFrame_(__import__("AppKit").NSMakeRect(16, path_y, text_width, PATH_HEIGHT))
        if self._response_label is not None:
            self._response_label.setFrame_(__import__("AppKit").NSMakeRect(16, _PAD_BOTTOM, text_width, reply_height))
        close = None if self._target is None else getattr(self._target, "close_button", None)
        if close is not None:
            # Keep the close mark in the top-right, above the wrapping reply.
            close_y = max(8, height - 36)
            close.setFrame_(__import__("AppKit").NSMakeRect(width - 40, close_y, 28, 28))
            if content is not None:
                try:
                    content.addSubview_positioned_relativeTo_(close, 1, None)
                except Exception:
                    log.exception("Could not keep the close button in front")


def _round_panel(content) -> None:
    """Round the popup. The window fill stays clear, so the corners are transparent."""
    from AppKit import NSColor

    content.setWantsLayer_(True)
    layer = content.layer()
    if layer is None:
        return
    red, green, blue, alpha = _FILL
    layer.setCornerRadius_(CORNER_RADIUS)
    layer.setMasksToBounds_(True)
    layer.setBackgroundColor_(
        NSColor.colorWithCalibratedRed_green_blue_alpha_(red, green, blue, alpha).CGColor()
    )


_RibbonContent = None


def _ribbon_content_class():
    global _RibbonContent
    if _RibbonContent is not None:
        return _RibbonContent
    from AppKit import NSBezierPath, NSColor, NSView

    red, green, blue, alpha = _FILL

    class RibbonContent(NSView):
        def isOpaque(self):
            return False

        def drawRect_(self, _dirty):
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                self.bounds(),
                CORNER_RADIUS,
                CORNER_RADIUS,
            )
            NSColor.colorWithCalibratedRed_green_blue_alpha_(red, green, blue, alpha).set()
            path.fill()

    _RibbonContent = RibbonContent
    return _RibbonContent


def _measured_height(label, text: str, width: int) -> int:
    """Height of the same wrapping field that draws the reply."""
    try:
        from AppKit import NSMakeRect

        cell = label.cell()
        cell.setWraps_(True)
        size = cell.cellSizeForBounds_(NSMakeRect(0, 0, width, 4000))
        return max(RESPONSE_LINE, int(size.height) + 2)
    except Exception:
        return response_height(text, width)


def _make_label(frame, size: float, bold: bool, wrap: bool = False):
    from AppKit import NSColor, NSFont, NSTextField

    label = NSTextField.alloc().initWithFrame_(frame)
    label.setEditable_(False)
    label.setBezeled_(False)
    label.setBordered_(False)
    label.setDrawsBackground_(False)
    label.setBackgroundColor_(NSColor.clearColor())
    label.setSelectable_(False)
    label.setUsesSingleLineMode_(not wrap)
    # 0 wraps at words. 5 clips one line with an ellipsis.
    label.setLineBreakMode_(0 if wrap else 5)
    cell = label.cell()
    if cell is not None:
        cell.setLineBreakMode_(0 if wrap else 5)
    if wrap:
        if hasattr(label, "setMaximumNumberOfLines_"):
            label.setMaximumNumberOfLines_(MAX_RESPONSE_ROWS)
        if cell is not None:
            cell.setWraps_(True)
            cell.setScrollable_(False)
    font = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
    label.setFont_(font)
    label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(0.12, 0.17, 0.23, 1))
    return label


def _on_main(fn) -> None:
    if sys.platform != "darwin":
        return
    try:
        from Foundation import NSThread
        from PyObjCTools import AppHelper
    except Exception:
        log.exception("AppKit is not available for the status ribbon")
        return
    if NSThread.isMainThread():
        try:
            fn()
        except Exception:
            log.exception("Could not update the status ribbon")
        return
    AppHelper.callAfter(fn)


class _RibbonActions:  # filled in as an NSObject subclass at runtime
    pass


def _install_actions() -> None:
    global _RibbonActions
    if sys.platform != "darwin":
        return
    from AppKit import NSObject

    class RibbonActions(NSObject):
        def close_(self, _sender):
            panel = getattr(self, "panel", None)
            if panel is not None:
                panel.orderOut_(None)

    _RibbonActions = RibbonActions


_install_actions()
