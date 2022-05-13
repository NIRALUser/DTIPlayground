from PyQt5.QtWidgets import * 
import os
import glob
import yaml
import dtiplayground.config as config

class SoftwarePaths(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)

        #self.setFixedWidth(800)
        self.setWindowTitle("Softwares")
        widget = QWidget()
        self.setCentralWidget(widget)

        layout = QGridLayout()
        widget.setLayout(layout)

        self.software_paths_filepath = os.path.expanduser("~/.niral-dti/dmriprep-" + config.INFO["dmriprep"]["version"] + "/software_paths.yml")
        self.software_paths_yml = yaml.safe_load(open(self.software_paths_filepath, 'r'))

        list_softwares = list(self.software_paths_yml["softwares"].keys())
        self.softwares_dict = {}

        for i in range(len(list_softwares)):
            layout.addWidget(QLabel(list_softwares[i]), i, 0)
            path = QLineEdit()
            path.setText(self.software_paths_yml["softwares"][list_softwares[i]]["path"])
            layout.addWidget(path, i, 1, 1, 5)
            self.softwares_dict[list_softwares[i]] = path

        button_cancel = QPushButton("Cancel")
        layout.addWidget(button_cancel, i+1, 5)
        button_cancel.clicked.connect(lambda: self.close())

        button = QPushButton("Save")
        layout.addWidget(button, i+1, 4)
        button.clicked.connect(self.UpdatePaths)

    def UpdatePaths(self):
        for software in self.softwares_dict.items():
            self.software_paths_yml["softwares"][software[0]] = {"path": software[1].text()}
        with open(self.software_paths_filepath, 'w')as filename:
            yaml.dump(self.software_paths_yml, filename)

        self.close()


