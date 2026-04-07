// @ts-check
// SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
//
// SPDX-License-Identifier: ISC

import starlight from "@astrojs/starlight";
import { defineConfig } from "astro/config";
import rehypeExternalLinks from "rehype-external-links";

export default defineConfig({
	site: "https://opencitations.github.io",
	base: "/ramose",
	integrations: [
		starlight({
			title: "RAMOSE",
			social: [
				{
					icon: "github",
					label: "GitHub",
					href: "https://github.com/opencitations/ramose",
				},
			],
			sidebar: [
				{ label: "Quick start", link: "/" },
				{
					label: "Guide",
					items: [
						"spec_file",
						"cli",
						"python_api",
						"parameters",
					],
				},
				{
					label: "Advanced",
					items: [
						"addons",
						"multi_source",
						"openapi",
					],
				},
			],
		}),
	],
	markdown: {
		rehypePlugins: [
			[rehypeExternalLinks, { target: "_blank", rel: ["noopener"] }],
		],
	},
});
