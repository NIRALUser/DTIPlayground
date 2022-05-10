from PyQt5.QtWidgets import * 
import os
import glob
import yaml
from functools import partial

class SoftwarePaths(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)


        self.setWindowTitle("Softwares")
        widget = QWidget()
        self.setCentralWidget(widget)

        layout = QGridLayout()
        widget.setLayout(layout)


        user_directory = os.path.expanduser("~/.niral-dti")
        list_of_dir = glob.glob(user_directory + "/*")
        if user_directory + "/user_preferences.yml" in list_of_dir:
          list_of_dir.remove(user_directory + "/user_preferences.yml")
        latest_dir = max(list_of_dir, key = os.path.getctime)
        self.software_paths_filepath = latest_dir + "/software_paths.yml"
        self.software_paths_yml = yaml.safe_load(open(self.software_paths_filepath, 'r'))

        list_softwares = list(self.software_paths_yml["softwares"].keys())
        self.softwares_dict = {}

        for i in range(len(list_softwares)):
            layout.addWidget(QLabel(list_softwares[i]), i, 0)
            path = QLineEdit()
            path.setText(self.software_paths_yml["softwares"][list_softwares[i]]["path"])
            layout.addWidget(path, i, 1, 1, 5)
            self.softwares_dict[list_softwares[i]] = path

        button = QPushButton("Ok")
        layout.addWidget(button, i+1, 1)
        button.clicked.connect(self.UpdatePaths)

    def UpdatePaths(self):
        for software in self.softwares_dict.items():
            self.software_paths_yml["softwares"][software[0]] = {"path": software[1].text()}
        with open(self.software_paths_filepath, 'w')as filename:
            yaml.dump(self.software_paths_yml, filename)

        self.close()


