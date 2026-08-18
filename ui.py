from PySide6 import QtCore, QtGui, QtWidgets
import compactor
import config
import copy
import json
import macro
import os
import player
import recorder
import sys


# Fields the details panel offers per step type. A caster of None shows the
# value without letting it be edited
FIELDS = {
    "click": [("x", int), ("y", int), ("button", str), ("hold_ms", int)],
    "mouse_down": [("x", int), ("y", int), ("button", str)],
    "mouse_up": [("x", int), ("y", int), ("button", str)],
    "scroll": [("x", int), ("y", int), ("dx", int), ("dy", int)],
    "move": [("from", None), ("to", None)],
    "type_text": [("text", str), ("delay_ms", int)],
    "key_press": [("key", str)],
    "key_down": [("key", str)],
    "key_up": [("key", str)],
    "wait": [("ms", int)],
}

# What the Insert menu offers, and a fresh one of each
NEW_STEPS = [
    ("Wait", {"type": "wait", "ms": 500}),
    ("Click", {"type": "click", "x": 0, "y": 0, "button": "left", "hold_ms": 80}),
    ("Type text", {"type": "type_text", "text": "", "delay_ms": config.TYPING_DELAY_MS}),
    ("Key press", {"type": "key_press", "key": "enter"}),
    ("Key down", {"type": "key_down", "key": "ctrl_l"}),
    ("Key up", {"type": "key_up", "key": "ctrl_l"}),
]

RUNNING_COLOUR = QtGui.QColor("#fff3bf")
DISABLED_COLOUR = QtGui.QColor("#9e9e9e")

# remembers the last macro between sessions, in the registry on windows
SETTINGS = QtCore.QSettings("PyReplay", "PyReplay")


class RecordThread(QtCore.QThread):
    """Runs the recorder, which blocks on its listener until the stop key."""

    done = QtCore.Signal(object)

    def run(self):
        self.done.emit(recorder.record())


class PlayThread(QtCore.QThread):
    """Runs the player off the UI thread, reporting progress by signal."""

    step_started = QtCore.Signal(int)
    ended = QtCore.Signal(bool)

    def __init__(self, steps: list, speed: float, repeats: int):
        super().__init__()
        self.steps = steps
        self.speed = speed
        self.repeats = repeats
        self.player = None

    def run(self):
        finished = True
        self.player = player.Player(self.speed, on_step=self.step_started.emit)

        for _ in range(self.repeats):
            finished = self.player.run(self.steps)
            if not finished:
                break

        self.ended.emit(finished)

    def stop(self):
        if self.player:
            self.player.aborted = True


class StepTree(QtWidgets.QTreeWidget):
    """The step list. Announces a drop once the move has settled."""

    reordered = QtCore.Signal()

    def dropEvent(self, event: QtGui.QDropEvent):
        super().dropEvent(event)
        self.reordered.emit()


class Details(QtWidgets.QWidget):
    """Property panel for the selected step, rebuilt whenever it changes."""

    about_to_change = QtCore.Signal()
    edited = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.step = None
        self.form = QtWidgets.QFormLayout(self)
        self.form.setLabelAlignment(QtCore.Qt.AlignRight)

    def show_step(self, step: dict):
        while self.form.rowCount():
            self.form.removeRow(0)

        self.step = step
        if step is None:
            return

        self.form.addRow("type", QtWidgets.QLabel(step["type"]))
        self.form.addRow("name", self.editor("name", str, step.get("name", "")))

        for key, caster in FIELDS.get(step["type"], []):
            if key not in step:
                continue

            if caster is None:
                self.form.addRow(key, QtWidgets.QLabel(str(step[key])))
            else:
                self.form.addRow(key, self.editor(key, caster, step[key]))

        if "path" in step:
            self.form.addRow("path", QtWidgets.QLabel("%s points" % len(step["path"])))

    def editor(self, key: str, caster, value) -> QtWidgets.QLineEdit:
        field = QtWidgets.QLineEdit(str(value))
        field.editingFinished.connect(lambda: self.write(field, key, caster))
        return field

    def write(self, field: QtWidgets.QLineEdit, key: str, caster):
        try:
            parsed = caster(field.text())
        except ValueError:
            field.setText(str(self.step.get(key, "")))
            return

        if parsed == self.step.get(key):
            return

        # announced first so the window can snapshot the step as it stands
        self.about_to_change.emit()

        # an empty name is the same as never setting one, and leaving the field
        # out is what keeps the compact guard meaningful
        if key == "name" and not parsed:
            self.step.pop("name", None)
        else:
            self.step[key] = parsed

        self.edited.emit()


class MainWindow(QtWidgets.QMainWindow):
    """
    Editor for a macro.

    self.steps is the model, the same list of dicts that lives in the json. The
    tree is a view rebuilt from it, and the only link between the two is the row
    index, since Qt copies item data and rebuilds items during a drag.
    """

    def __init__(self, path: str = None):
        super().__init__()
        self.resize(1150, 680)

        self.steps = []
        self.path = None
        self.dirty = False
        self.undone = []
        self.redone = []

        self.populating = False
        self.running_row = None
        self.inserting_recording = False
        self.record_thread = None
        self.play_thread = None

        self.build()

        if path and os.path.exists(path):
            self.open(path)
        else:
            self.mark_dirty(False)

    ### Layout

    def build(self):
        self.build_widgets()
        self.build_menus()
        self.build_toolbar()

        split = QtWidgets.QSplitter()
        split.addWidget(self.tree)
        split.addWidget(self.details)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)

        self.setCentralWidget(split)
        self.statusBar()
        self.update_undo_actions()

    def build_widgets(self):
        self.tree = StepTree()
        self.tree.setHeaderLabels(["Index", "Action", "Label"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tree.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.tree.setColumnWidth(0, 70)
        self.tree.setColumnWidth(1, 420)
        self.tree.itemSelectionChanged.connect(self.selection_changed)
        self.tree.itemChanged.connect(self.item_changed)
        self.tree.reordered.connect(self.reorder)

        self.details = Details()
        self.details.about_to_change.connect(lambda: self.snapshot())
        self.details.edited.connect(self.refresh_selected_rows)

    def build_menus(self):
        files = self.menuBar().addMenu("&File")
        files.addAction("&New", QtGui.QKeySequence.New, self.new)
        files.addAction("&Open...", QtGui.QKeySequence.Open, self.open_dialog)
        files.addAction("&Save", QtGui.QKeySequence.Save, self.save)
        files.addAction("Save &As...", QtGui.QKeySequence.SaveAs, self.save_as)

        edit = self.menuBar().addMenu("&Edit")
        self.undo_action = edit.addAction("&Undo", QtGui.QKeySequence.Undo, self.undo)
        self.redo_action = edit.addAction("&Redo", QtGui.QKeySequence.Redo, self.redo)
        edit.addSeparator()

        # scoped to the tree, or they would swallow ctrl+c and delete from the
        # text fields in the details panel
        for label, shortcut, slot in (
                ("Cu&t", QtGui.QKeySequence.Cut, self.cut_selected),
                ("&Copy", QtGui.QKeySequence.Copy, self.copy_selected),
                ("&Paste", QtGui.QKeySequence.Paste, self.paste),
                ("&Delete", QtGui.QKeySequence.Delete, self.delete_selected)):
            action = edit.addAction(label, shortcut, slot)
            action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
            self.tree.addAction(action)

        insert = self.menuBar().addMenu("&Insert")
        insert.addAction("&Recording...", lambda: self.start_recording(True))
        insert.addSeparator()

        for label, template in NEW_STEPS:
            insert.addAction(label, lambda t=template: self.add_steps([t], "inserted"))

    def build_toolbar(self):
        bar = self.addToolBar("main")
        bar.setMovable(False)

        # lambdas because Qt passes the action's checked state as the first
        # argument, which is not what start_recording means by it
        self.record_action = bar.addAction("Record", lambda: self.start_recording(False))
        self.play_action = bar.addAction("Play", self.start_playback)
        self.stop_action = bar.addAction("Stop", self.stop_playback)
        self.stop_action.setEnabled(False)
        bar.addSeparator()

        self.repeats = QtWidgets.QSpinBox()
        self.repeats.setRange(1, 999)
        self.repeats.setPrefix("repeat  ")
        bar.addWidget(self.repeats)

        self.speed = QtWidgets.QDoubleSpinBox()
        self.speed.setRange(0.1, 20.0)
        self.speed.setSingleStep(0.5)
        self.speed.setValue(config.PLAYBACK_SPEED)
        self.speed.setPrefix("speed  ")
        bar.addWidget(self.speed)

        bar.addSeparator()
        bar.addAction("Save", self.save)
        bar.addAction("Delete", self.delete_selected)

    ### Undo

    def snapshot(self):
        """Keep the steps as they are, before whatever is about to change them."""
        # a deep copy because the details panel edits steps in place
        self.undone.append(copy.deepcopy(self.steps))
        del self.undone[:-config.UNDO_DEPTH]

        self.redone.clear()
        self.mark_dirty()
        self.update_undo_actions()

    def travel(self, back: list, forward: list, verb: str):
        """Undo and redo are the same move in opposite directions."""
        if not back:
            return

        forward.append(copy.deepcopy(self.steps))
        self.steps = back.pop()

        self.populate()
        self.mark_dirty()
        self.update_undo_actions()
        self.status(verb)

    def undo(self):
        self.travel(self.undone, self.redone, "undone")

    def redo(self):
        self.travel(self.redone, self.undone, "redone")

    def update_undo_actions(self):
        self.undo_action.setEnabled(bool(self.undone))
        self.redo_action.setEnabled(bool(self.redone))

    ### Files

    def mark_dirty(self, dirty: bool = True):
        self.dirty = dirty
        self.setWindowTitle("%s%s - PyReplay"
                            % (os.path.basename(self.path) if self.path else "untitled",
                               " *" if dirty else ""))

    def confirm_discard(self) -> bool:
        """Ask about unsaved work. False means the caller should stop."""
        if not self.dirty:
            return True

        choice = QtWidgets.QMessageBox.question(
            self, "Unsaved changes",
            "Save changes to %s?" % (os.path.basename(self.path) if self.path
                                     else "untitled"),
            QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard
            | QtWidgets.QMessageBox.Cancel)

        if choice == QtWidgets.QMessageBox.Cancel:
            return False
        if choice == QtWidgets.QMessageBox.Save:
            return self.save()

        return True

    def adopt(self, steps: list, path: str, dirty: bool):
        """The macro is now this one. History does not carry across."""
        self.steps = steps
        self.path = path
        self.undone.clear()
        self.redone.clear()

        # a different macro, so the old selection means nothing
        self.populate(keep_selection=False)
        self.mark_dirty(dirty)
        self.update_undo_actions()

    def new(self):
        if self.confirm_discard():
            self.adopt([], None, False)
            self.status("new macro")

    def open(self, path: str):
        try:
            steps = macro.load(path)
        except (OSError, KeyError, ValueError) as error:
            self.status("could not open %s: %s" % (path, error))
            return

        self.adopt(steps, path, False)
        SETTINGS.setValue("last_macro", path)
        self.status("opened %s" % path)

    def open_dialog(self):
        if not self.confirm_discard():
            return

        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open macro", config.MACROS_DIR, "Macros (*.json)")

        if path:
            self.open(path)

    def save(self) -> bool:
        if not self.path:
            return self.save_as()

        macro.save(self.steps, self.path)
        SETTINGS.setValue("last_macro", self.path)
        self.mark_dirty(False)
        self.status("saved %s" % self.path)
        return True

    def save_as(self) -> bool:
        os.makedirs(config.MACROS_DIR, exist_ok=True)

        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save macro", config.MACROS_DIR, "Macros (*.json)")

        if not path:
            return False

        self.path = path
        return self.save()

    def closeEvent(self, event: QtGui.QCloseEvent):
        if self.confirm_discard():
            event.accept()
        else:
            event.ignore()

    ### The step list

    def populate(self, keep_selection: bool = True):
        # rebuilding drops the selection, so put it back or an undo would empty
        # the details panel every time
        selected = self.rows(self.tree.selectedItems()) if keep_selection else []

        # itemChanged fires while rows are built, so suppress the handler rather
        # than let it write half-built rows back to the model
        self.populating = True
        self.tree.clear()

        for step in self.steps:
            self.tree.addTopLevelItem(self.make_item(step))

        self.renumber()
        self.populating = False

        self.select_rows([row for row in selected if row < len(self.steps)])
        self.status()

    def make_item(self, step: dict) -> QtWidgets.QTreeWidgetItem:
        item = QtWidgets.QTreeWidgetItem(["", macro.summarise(step), step.get("name", "")])

        # a drop onto a row would nest the dragged step under it, which a flat
        # list cannot express. only drops between rows count
        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsDropEnabled)

        item.setCheckState(0, QtCore.Qt.Checked if step.get("enabled", True)
                           else QtCore.Qt.Unchecked)
        self.paint(item, step)
        return item

    def paint(self, item: QtWidgets.QTreeWidgetItem, step: dict):
        greyed = not step.get("enabled", True)
        for column in range(3):
            item.setForeground(column, QtGui.QBrush(DISABLED_COLOUR) if greyed
                               else QtGui.QBrush())

    def renumber(self):
        for row in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(row).setText(0, str(row))

    def rows(self, items: list) -> list:
        return [self.tree.indexOfTopLevelItem(item) for item in items]

    def reorder(self):
        # the index column still holds each row's position from before the drop,
        # which is what says where every step came from
        order = [int(self.tree.topLevelItem(row).text(0))
                 for row in range(self.tree.topLevelItemCount())]

        # a row that landed anywhere but the top level would be missing here
        if sorted(order) != list(range(len(self.steps))):
            self.populate()
            self.status("that drop would have lost a step, nothing moved")
            return

        self.snapshot()
        self.steps = [self.steps[was] for was in order]
        self.renumber()
        self.selection_changed()

    def item_changed(self, item: QtWidgets.QTreeWidgetItem, _column: int):
        if self.populating:
            return

        row = self.tree.indexOfTopLevelItem(item)
        if not 0 <= row < len(self.steps):
            return

        step = self.steps[row]
        enabled = item.checkState(0) == QtCore.Qt.Checked
        if enabled == step.get("enabled", True):
            return

        self.snapshot()

        # absent means enabled, so drop the field rather than write the default
        if enabled:
            step.pop("enabled", None)
        else:
            step["enabled"] = False

        self.paint(item, step)
        self.status()

    def selection_changed(self):
        rows = self.rows(self.tree.selectedItems())
        self.details.show_step(self.steps[rows[0]] if rows else None)

    def refresh_selected_rows(self):
        for item in self.tree.selectedItems():
            step = self.steps[self.tree.indexOfTopLevelItem(item)]
            item.setText(1, macro.summarise(step))
            item.setText(2, step.get("name", ""))

    def select_rows(self, rows):
        self.tree.clearSelection()
        items = [self.tree.topLevelItem(row) for row in rows]

        if items and items[0]:
            self.tree.setCurrentItem(items[0])

        for item in items:
            if item:
                item.setSelected(True)

    def add_steps(self, new: list, verb: str):
        """Put steps in below the selection, or at the end if there is none."""
        rows = self.rows(self.tree.selectedItems())
        at = max(rows) + 1 if rows else len(self.steps)

        self.snapshot()
        # copied so two inserted waits are two steps, not one shared dict
        self.steps[at:at] = copy.deepcopy(new)

        self.populate()
        self.select_rows(range(at, at + len(new)))
        self.status("%s %s step(s)" % (verb, len(new)))

    def delete_selected(self):
        rows = self.rows(self.tree.selectedItems())
        if not rows:
            return

        self.snapshot()

        # highest first, so removing one does not shift the rest
        for row in sorted(rows, reverse=True):
            self.tree.takeTopLevelItem(row)
            del self.steps[row]

        self.renumber()
        self.status("deleted %s" % len(rows))

    ### Clipboard

    def copy_selected(self):
        # the system clipboard rather than an attribute, so steps survive
        # opening another macro and can be pasted into a text editor
        rows = sorted(self.rows(self.tree.selectedItems()))
        if not rows:
            return

        copied = [self.steps[row] for row in rows]
        QtWidgets.QApplication.clipboard().setText(json.dumps(copied, indent=2))
        self.status("copied %s step(s)" % len(copied))

    def cut_selected(self):
        self.copy_selected()
        self.delete_selected()

    def paste(self):
        try:
            pasted = json.loads(QtWidgets.QApplication.clipboard().text())
        except ValueError:
            pasted = None

        # the clipboard holds whatever was last copied anywhere, so check it
        # looks like steps before letting it into the macro
        if (not isinstance(pasted, list) or not pasted
                or not all(isinstance(step, dict) and "type" in step for step in pasted)):
            self.status("the clipboard does not hold steps")
            return

        self.add_steps(pasted, "pasted")

    ### Recording and playback

    def start_recording(self, insert: bool):
        """Record either a new macro, or steps to drop into this one."""
        # only a replacement can lose work, and the selection says where an
        # insert goes, so leave both alone when inserting
        if not insert and not self.confirm_discard():
            return

        self.inserting_recording = insert
        self.hide()   # otherwise clicking around this window lands in the macro

        self.record_thread = RecordThread()
        self.record_thread.done.connect(self.recording_finished)
        self.record_thread.start()

    def recording_finished(self, events: list):
        recorder.save(events, config.RECORDING_PATH)
        steps = compactor.compact(events)

        if self.inserting_recording:
            self.add_steps(steps, "recorded")
        else:
            # untitled, so a recording never writes over the open macro
            self.adopt(steps, None, True)

        self.show()
        self.status("recorded %s events into %s step(s)" % (len(events), len(steps)))

    def start_playback(self):
        if not self.steps:
            return

        self.play_action.setEnabled(False)
        self.record_action.setEnabled(False)
        self.stop_action.setEnabled(True)

        self.play_thread = PlayThread(self.steps, self.speed.value(),
                                      self.repeats.value())
        self.play_thread.step_started.connect(self.highlight)
        self.play_thread.ended.connect(self.playback_finished)
        self.play_thread.start()

    def stop_playback(self):
        if self.play_thread:
            self.play_thread.stop()

    def highlight(self, row: int):
        if self.running_row is not None:
            self.shade(self.running_row, QtGui.QBrush())

        self.shade(row, QtGui.QBrush(RUNNING_COLOUR))
        self.tree.scrollToItem(self.tree.topLevelItem(row))
        self.running_row = row

    def shade(self, row: int, brush: QtGui.QBrush):
        item = self.tree.topLevelItem(row)
        if item is None:
            return

        for column in range(3):
            item.setBackground(column, brush)

    def playback_finished(self, finished: bool):
        if self.running_row is not None:
            self.shade(self.running_row, QtGui.QBrush())
            self.running_row = None

        self.play_action.setEnabled(True)
        self.record_action.setEnabled(True)
        self.stop_action.setEnabled(False)
        self.status("finished" if finished else "aborted")

    def status(self, message: str = ""):
        disabled = sum(1 for step in self.steps if not step.get("enabled", True))
        self.statusBar().showMessage(
            "%s steps%s   %s" % (len(self.steps),
                                 ", %s disabled" % disabled if disabled else "",
                                 message))


def run():
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow(SETTINGS.value("last_macro", ""))
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()