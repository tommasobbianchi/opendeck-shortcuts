// Excerpt from OrcaSlicer src/slic3r/GUI/KBShortcutsDialog.cpp
// Test fixture: only the shapes the provider parses are exercised here.

Shortcuts global_shortcuts = {
    { ctrl + "N", L("New Project") },
    { ctrl + shift + "S", L("Save Project as")},
    { "A", L("Arrange all objects") },
    { L("Esc"), L("Deselect all") },
#ifdef __APPLE__
    {"fn+⌫", L("Delete selected")},
#else
    {L("Del"), L("Delete selected")},
#endif
    { ctrl + L("Mouse wheel"), L("Zoom View") },
    { "1-9", L("Keyboard 1-9: set filament for object/part") },
};

Shortcuts preview_shortcuts = {
    { L("Arrow Up"), L("Move up") },
};
