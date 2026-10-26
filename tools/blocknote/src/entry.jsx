// Hermes Notes editor: BlockNote behind a small vanilla-JS API.
//
// The WebUI has no bundler and no React, so this file is built once (see
// build.mjs) into static/vendor/blocknote/<version>/ and the Notes page
// imports it lazily. Everything React stays inside this module; the page only
// sees mountNoteEditor() and the controller it returns.
//
// One editor instance per open note: switching notes creates a fresh editor
// so undo history never crosses from one note into another, and nothing
// replaces content under an editor the user is typing in.
import { BlockNoteEditor, filterSuggestionItems } from "@blocknote/core";
import { BlockNoteView } from "@blocknote/mantine";
import { SuggestionMenuController, getDefaultReactSlashMenuItems } from "@blocknote/react";
import "@blocknote/mantine/style.css";
import { createElement } from "react";
import { createRoot } from "react-dom/client";

export const BLOCKNOTE_VERSION = "0.55.0";

// Slash-menu items that change what kind of line it is. BlockNote applies
// them to the current line only when it is empty; on a line with text it
// inserts a new block below. These keep the text and change the line itself,
// as a word processor's paragraph styles do. Items that add something
// (image, table, divider, file...) still go below.
const LINE_FORMATS = {
  quote: { type: "quote" },
  toggle_list: { type: "toggleListItem" },
  numbered_list: { type: "numberedListItem" },
  bullet_list: { type: "bulletListItem" },
  check_list: { type: "checkListItem" },
  paragraph: { type: "paragraph" },
  code_block: { type: "codeBlock" },
};

function lineFormat(editor, key) {
  const heading = /^(toggle_)?heading(?:_(\d))?$/.exec(String(key || ""));
  if (!heading) return LINE_FORMATS[key];
  const props = { level: Number(heading[2] || 1) };
  if (editor.schema.blockSchema.heading?.propSchema?.isToggleable) props.isToggleable = !!heading[1];
  return { type: "heading", props };
}

function formatsTheLine(editor, item) {
  const format = lineFormat(editor, item.key);
  if (!format) return item;
  return {
    ...item,
    onItemClick: () => {
      // By now the menu has removed the "/query" it was opened with.
      const line = editor.getTextCursorPosition().block;
      if (!Array.isArray(line.content) || !line.content.length) return item.onItemClick();
      const updated = editor.updateBlock(line, format);
      if (editor.getTextCursorPosition().block.id !== updated.id) editor.setTextCursorPosition(updated, "end");
    },
  };
}

function normaliseContent(content) {
  return Array.isArray(content) && content.length ? content : undefined;
}

/**
 * Mount an editor into `host`.
 *
 * options:
 *   content       BlockNote document (array of blocks) or null for an empty note
 *   theme         "light" | "dark"
 *   editable      default true
 *   placeholder   text for the empty first block
 *   uploadFile    async (File) => url   (images/files; omit to disable uploads)
 *   onChange      () => void            (fires on user edits only)
 *   slashItems    (editor) => extra slash-menu items (extension point; see docs/notes.md)
 */
export function mountNoteEditor(host, options = {}) {
  const editor = BlockNoteEditor.create({
    initialContent: normaliseContent(options.content),
    uploadFile: typeof options.uploadFile === "function" ? options.uploadFile : undefined,
    placeholders: options.placeholder ? { default: options.placeholder, emptyDocument: options.placeholder } : undefined,
  });
  let theme = options.theme === "dark" ? "dark" : "light";
  let editable = options.editable !== false;
  const root = createRoot(host);
  const getItems = async (query) => {
    const extra = typeof options.slashItems === "function" ? options.slashItems(editor) || [] : [];
    const items = getDefaultReactSlashMenuItems(editor).map((item) => formatsTheLine(editor, item));
    return filterSuggestionItems([...items, ...extra], query);
  };
  const render = () => {
    root.render(
      createElement(
        BlockNoteView,
        {
          editor,
          theme,
          editable,
          slashMenu: false,
          onChange: () => { if (typeof options.onChange === "function") options.onChange(); },
          className: "hermes-note-editor",
        },
        createElement(SuggestionMenuController, { triggerCharacter: "/", getItems }),
      ),
    );
  };
  render();

  return {
    editor,
    getBlocks: () => editor.document,
    toMarkdown: () => editor.blocksToMarkdownLossy(editor.document),
    toHTML: () => editor.blocksToFullHTML(editor.document),
    parseMarkdown: (markdown) => editor.tryParseMarkdownToBlocks(String(markdown || "")),
    parseHTML: (html) => editor.tryParseHTMLToBlocks(String(html || "")),
    replaceAll: (blocks) => {
      if (Array.isArray(blocks) && blocks.length) editor.replaceBlocks(editor.document, blocks);
    },
    insertBlocksAtEnd: (blocks) => {
      const doc = editor.document;
      editor.insertBlocks(blocks, doc[doc.length - 1], "after");
    },
    focus: () => editor.focus(),
    setTheme: (next) => { theme = next === "dark" ? "dark" : "light"; render(); },
    setEditable: (next) => { editable = next !== false; render(); },
    destroy: () => { root.unmount(); },
  };
}
