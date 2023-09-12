import json

from pathlib import Path
from rich.text import Text

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Tree
from textual.widgets.tree import TreeNode


class ModExplorer(Widget):
    BINDINGS = []

    def __init__(self, json_path: Path):
        self.json_path = json_path
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Tree("Root")

    @classmethod
    def add_json(cls, name: str, node: TreeNode, json_data: object) -> None:
        """Adds JSON data to a node.

        Args:
            node (TreeNode): A Tree node.
            json_data (object): An object decoded from JSON.
        """

        from rich.highlighter import ReprHighlighter

        highlighter = ReprHighlighter()

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
                        new_name = f"{index} - {value['Name']}"
                        if "Nickname" in value and value["Nickname"] != "":
                            new_name += f" ({value['Nickname']})"
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

    def on_mount(self) -> None:
        with open(self.json_path) as data_file:
            self.json_data = json.load(data_file)
        tree = self.query_one(Tree)
        tree.show_root = not tree.show_root
        json_node = tree.root.add("ROOT")
        self.add_json(str(self.json_path), json_node, self.json_data)
