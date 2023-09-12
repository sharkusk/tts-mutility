import json

from rich.text import Text
from rich.highlighter import ReprHighlighter

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Tree
from textual.widgets.tree import TreeNode


class ModExplorer(Widget):
    BINDINGS = []

    def __init__(self, json_path, *, json_data=None, start_trail=[]):
        self.json_path = json_path
        self.json_data = json_data
        self.trail = start_trail
        self.start_node = None
        super().__init__()

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
                if len(value) > 80:
                    value = value[:77] + "..."
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
        tree.scroll_to_node(node)
        tree.select_node(node)

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
