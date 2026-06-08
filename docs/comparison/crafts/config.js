const config = {
	port: 8888,

	userPath: "users",
	apisPath: "apis",
	dumpsPath: "dumps",
	dataPath: "data",

	scheme: "http",
	authority: "localhost:8085",
	prepath: "",

	usersFile: "users.json",
	listDumpFileEnding: "_dumpIndex.json",

	nolang: "nolang",

	root: 'changeme',
	rootEmail: 'root@example.com',

	daysCache: 3,
	millisecsCleanCache: 60*60*1000
}

module.exports = config
