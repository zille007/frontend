There are two separate servers: frontend (frontend.py) and game server itself (entrypoint RunServer.py). Both have there own config file (config.py or something like that) that contain all the basic configurationa. Both frontend- and backend server have been written with Python 2.7, Python 3.x may work with small changes, but has not been tested.

Backend server needs a connection to a mongodb-database which contains all solid entity and map datas. The latest mongoDB dump is in mongo_database_dump.zip -file. All data within the file is in mongoDB:s dump format, so it can be restored with mongorestore (see mongoDB documentation for more information)

Frontend server needs access to a postgres-database, which needs to be setup with database structures from database.py. You can use Python's sqlalchemy to restore said data structures. create_postgresql_database.zip contains a modified database.py which I have used when creating postgresql data structures so that may be of some help.
 
When postgresql is up and running with the correct databases you can add users to its users-table. (Note currently there is no automated way to add users to the game, so you will either need to do it manually or create an automated way)
 
mongoDB address and port information is needed in both frontend and backend configuration files. Postgresql is needed only in frontend. 

Frontend server supports multiple backend servers (it launches new games in a random backend server). At least one backend server is needed in order to run the game.
 
Backend server has been written with Python's twisted -networkinterface, so that and txmongo dependencies are needed. The easiest way to install needed dependencies is probably pip.

Frontend server needs the following dependencies:
- gevent and all the dependencies it requires
- psycopg2
- psycogreen
- bottle
- pymongo
- sqlalchemy
 
When all dependencies are in place, databases setup correctly and server configurations done you can start both servers by running there respective launch scripts with python (frontend.py for frontend server and RunServer.py for backend server)
 
Both servers can be run with any JIT-compiling Python implementation f.ex. pypy, but that is not mandatory. 

Frontend server address and port need to be configured to the Unity project.




_____________________________________
recommend setting up two linux servers (I used Linux AMI in Amazon cloud) that you can access with an ssh connection. In my setup mongoDB, postgresql and frontend server were running on one server, and backend server was running on the other. You will not need to buy any components. everything is available via normal linux package management for free. 

Regarding postgresql:
After you have installed python 2.7.x (+ the dependencies listed in the instructions) and postgresql server via package management, you should be able to initialize the needed database structures simply by running the file in create_postgresql_database_structures.zip (python create_postgresql_database.py). After that is done you can insert a test user with the username test1 and password test via typing the following command to postgresql shell: 

INSERT INTO users VALUES (91, 'test1', 'test1', '098f6bcd4621d373cade4e832627b4f6', 'BETA', True, 0, 1500, 'emailaddress'); 

Backend server config file is called ServerConfig.py and frontend server config file is FrontendConfig.py.

Commands to install python dependencies (these should work without issues after Python has been installed):
pip install twisted
pip install txmongo
pip install gevent
pip install psycopg2
pip install psycogreen
pip install bottle
pip install pymongo
pip install sqlalchemy

I hope this will help you further with the setup process. 
____________________________________________________________________________

Instructions in a nutshell:
1) Install mongodb
2) Install postgres
3) Import solid data to mongodb (mongorestore, mongoDB database must be named tatd)
4) Create postgres-tables (check database.py and create_postgresql_database.zip).
5) Make sure that both mongodb and postgres have a read / write enable user
6) Update mongoDB and postgres address, port, username and password to server configuration files
7) Change the bind address in both the frontend and backend server, and update those to there respective configuration files
8) Make sure that those addresses and ports are accessible for needed IP-addresses
9) Install twisted and txmongo to the backend server with pip (if you want to use a virtual environment check http://docs.python-guide.org/en/latest/dev/virtualenvs/ )
10) Start backend server (python RunServer.py)
11) Install all the python dependencies, that frontend server needs, with pip
12) Start frontend server (python frontend.py)
13) Update frontend server IP to the Unity project and compile it (note that this project has been developed with Unity 3D v. 4.x. 5.x. will not be able to compile the project without some modification)
14) Compile project with Unity 3D
15) Play
