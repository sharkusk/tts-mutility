import json
from webbrowser import open as open_url

from rich.highlighter import ReprHighlighter
from rich.text import Text
from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from ..dialogs.InfoDialog import TextDialog


class ModExplorer(Widget):
    BINDINGS = []

    def __init__(self, json_path, *, json_data=None, start_trail=[], **kwargs):
        self.json_path = json_path
        self.json_data = json_data
        self.trail = start_trail
        self.start_node = None
        self.text_values = []
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Tree("Root")

    def add_json(self, name: str, node: TreeNode, json_data: object) -> None:
        """Adds JSON data to a node.

        Args:
            node (TreeNode): A Tree node.
            json_data (object): An object decoded from JSON.
        """

        highlighter = ReprHighlighter()

        # ObjectStates -> "Infinite_Bag KOBAN (f591f5)" -> ContainedObjects -> "Koban (32c4ff)" -> CustomMesh -> DiffuseURL

        def add_node(name: str, node: TreeNode, data: object) -> None:
            """Adds a node to the tree.

            Args:
                name (str): Name of the node.
                node (TreeNode): Parent node.
                data (object): Data associated with the node.
            """
            if isinstance(data, dict):
                node.set_label(Text(f"{{{len(data)}}} {name}"))
                for key, value in data.items():
                    new_node = node.add("")
                    add_node(key, new_node, value)
            elif isinstance(data, list):
                node.set_label(Text(f"[{len(data)}] {name}"))
                for index, value in enumerate(data):
                    new_node = node.add("")
                    if isinstance(value, dict) and "Name" in value:
                        new_name = f"{index} - "
                        if "GUID" in value and value["GUID"] != "":
                            new_name += f"({value['GUID']}) "
                        new_name += f"{value['Name']} "
                        if "Nickname" in value and value["Nickname"] != "":
                            new_name += f"({value['Nickname']})"
                    else:
                        new_name = str(index)
                    add_node(new_name, new_node, value)
            else:
                node.allow_expand = False
                value = repr(data)
                if str(data)[0:4] == "http" or (name and "URL" in name):
                    label = ""
                    if name:
                        label += f"{name}="
                    if len(value) > 50:
                        link_value = value[:46] + "..."
                    else:
                        link_value = value
                    label += f"[@click=link_clicked({value})]{link_value}[/]"
                elif len(value) > 50:
                    label = ""
                    if name:
                        label += f"{name}="
                        if "lua" in name.lower():
                            self.text_values.append(
                                Syntax(str(data), "lua", line_numbers=True)
                            )
                        elif "xml" in name.lower():
                            self.text_values.append(
                                Syntax(str(data), "xml", line_numbers=True)
                            )
                        else:
                            self.text_values.append(highlighter(str(data)))
                    else:
                        self.text_values.append(highlighter(str(data)))
                    short_value = value[:45] + "..." + value[0]
                    label += f"[@click=text_clicked({len(self.text_values)-1})]{short_value}[/]"
                else:
                    if name:
                        label = Text.assemble(
                            Text.from_markup(f"[b]{name}[/b]="), highlighter(value)
                        )
                    else:
                        label = Text(value)
                node.set_label(label)

        add_node(name, node, json_data)

    def jump_to_node(self, node):
        tree = self.query_one(Tree)
        tree.select_node(node)
        tree.select_node(node)
        self.call_after_refresh(self.update_scroll)

    def update_scroll(self):
        tree = self.query_one(Tree)
        line = tree.cursor_line
        tree.scroll_to_line(line)

    def find_node(self, trail: list, expand: bool = True) -> TreeNode:
        tree = self.query_one(Tree)
        node = tree.root.children[0]
        if expand:
            node.expand()
        while len(trail) > 0:
            for child in node.children:
                if trail[0][0] == '"':
                    # This is a "Name + (GUID)", we only want the GUID for our trail
                    trail[0] = trail[0][trail[0].rfind("(") + 1 : trail[0].rfind(")")]
                if trail[0] in str(child.label):
                    trail = trail[1:]
                    node = child
                    if expand:
                        node.expand()
                    break
            else:
                # Didn't find this path, so return the closest that we found
                break

        return node

    def on_mount(self) -> None:
        if self.json_data is None:
            with open(self.json_path, encoding="utf-8") as data_file:
                self.json_data = json.load(data_file)
        tree = self.query_one(Tree)
        tree.auto_expand = True
        tree.show_root = False
        json_node = tree.root.add("ROOT")
        self.add_json(str(self.json_path), json_node, self.json_data)

        if len(self.trail) > 0:
            self.start_node = self.find_node(self.trail)
        else:
            self.start_node = tree.root.children[0]
            self.start_node.expand()

        self.call_after_refresh(self.jump_to_node, self.start_node)

        tree.action_link_clicked = self.action_link_clicked
        tree.action_text_clicked = self.action_text_clicked

    def action_link_clicked(self, url: str):
        open_url(url)

    def action_text_clicked(self, i: str):
        self.app.push_screen(TextDialog(self.text_values[int(i)]))
