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

	defaultOptions: {
		compactQueries: true,
		singletonArrays: "collapse",
		cache: {
			maxSize: 1024 * 1024 * 512,
			ttl: 1000 * 60 * 60 * 24 * 3,
			ttlAutopurge: true,
			updateAgeOnGet: true
		},
		endpoints: {
			queryPostThreshold: 4 * 1024,
			maxConcurrentQueries: { defaultValue: 4, min: 1, max: 32 },
			resourcePage: { defaultValue: 100, min: 10, max: 300 },
			limit: { defaultValue: 10000, min: 1000, max: 100000 }
		}
	}
}

module.exports = config
