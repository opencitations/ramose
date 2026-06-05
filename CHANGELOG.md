# [2.2.0](https://github.com/opencitations/ramose/compare/v2.1.0...v2.2.0) (2026-06-05)


### Bug Fixes

* **openapi:** filter disabled params from components and infer schema from output_json ([3f3261e](https://github.com/opencitations/ramose/commit/3f3261e82b80eba73f945e8c869ac19a6e2c8533))
* **skgif:** emit url scheme for Zenodo and SWH identifiers in Wikidata API ([b68ab38](https://github.com/opencitations/ramose/commit/b68ab386eeee4cdea376714f01c4511c606be174))


### Features

* **skgif:** omit empty optional fields from JSON-LD output ([aefcb52](https://github.com/opencitations/ramose/commit/aefcb5271ae9bfbe966fa79777ffe5b409c38f3f))
* **skgif:** switch ORKG example to HERITRACE and extract richer metadata ([fd889bb](https://github.com/opencitations/ramose/commit/fd889bbdef8815ba4646aef7ef7635fb96dd8c75))

# [2.1.0](https://github.com/opencitations/ramose/compare/v2.0.0...v2.1.0) (2026-05-25)


### Bug Fixes

* **api_manager:** return 400 instead of 404 for invalid parameter values ([f26a6c0](https://github.com/opencitations/ramose/commit/f26a6c05d515d4c93cdb26ef34a9fcdef8e6ded7)), closes [#19](https://github.com/opencitations/ramose/issues/19)
* **cache:** allow cross-thread access and simplify cache keys ([281a307](https://github.com/opencitations/ramose/commit/281a3075e617b7d97bb9901d67f56d2fcdb879ce))
* **ci:** avoid uv cache race condition across matrix jobs ([30ed037](https://github.com/opencitations/ramose/commit/30ed037fcaf4becaa381f0f2b0b306ca4525bf57))
* **docs:** clean up operation descriptions and parameter rendering ([5a40cc9](https://github.com/opencitations/ramose/commit/5a40cc9a81744140e07c229ff451c88d9c03e12a))
* **docs:** hide result fields type when default format is custom ([ce4b52e](https://github.com/opencitations/ramose/commit/ce4b52ea4150081699458a11e17893fb5898d723)), closes [#default_format](https://github.com/opencitations/ramose/issues/default_format)
* **docs:** improve accessibility and readability of HTML documentation ([4eff0a5](https://github.com/opencitations/ramose/commit/4eff0a5e6e21deef35c6d5aef1781becbb942a22)), closes [#808080](https://github.com/opencitations/ramose/issues/808080) [#595959](https://github.com/opencitations/ramose/issues/595959)
* **docs:** render parameters as proper html lists and handle optional field_type ([4e5bbcc](https://github.com/opencitations/ramose/commit/4e5bbcc494cdbd905a4164794897dab5dde27fe7))
* **paging:** delegate pagination to format converters ([5b79cfb](https://github.com/opencitations/ramose/commit/5b79cfba21e64d3237f3eb4eebb6ea3fa2e980c1))
* **skg-if:** pass through local identifier and raise ValueError when the field is missing ([b465b35](https://github.com/opencitations/ramose/commit/b465b3569d0e9d09f1105c85d3ba0c96c4c66473))
* **skg-if:** produce structured titles/abstracts when lang columns are absent ([572bb70](https://github.com/opencitations/ramose/commit/572bb70e9472cdf8d6a26717de3d68a7b50152c9))
* **skg-if:** single-entity endpoints now return 404 when the entity is not found ([5f24550](https://github.com/opencitations/ramose/commit/5f24550d8fc05e566cfd6b12c926877c3585eddb))
* **skgif:** align products endpoint output with SKG-IF OpenAPI spec ([50251bc](https://github.com/opencitations/ramose/commit/50251bc487ee5ab943449e23d7fdcc7928e0834e))
* **skgif:** produce valid xsd:dateTime values in normalized dates ([695fd44](https://github.com/opencitations/ramose/commit/695fd44696c59c5a667f50d67fd0b6f553fd908b))
* **skgif:** validate product_type filter against SKG-IF spec ([24e36b4](https://github.com/opencitations/ramose/commit/24e36b4bb39a081490464e064d332243c7c57503))
* **test:** add missing pyshacl and rdflib dev dependencies ([2e352e1](https://github.com/opencitations/ramose/commit/2e352e1e193aa4e1998010d495d44b37226eeba4))
* **test:** change parameter rendering from <p> to <div> in tests ([18c33c5](https://github.com/opencitations/ramose/commit/18c33c5a45577a6f917beb6f2894529859b85cfd))
* **test:** patch SparqlAnything in the correct module namespace ([5beccff](https://github.com/opencitations/ramose/commit/5beccff020b1d38b8e118ddb3e5048d1e91ceeb5))
* **test:** stub pysparql_anything module when optional extra not installed ([a27f0d3](https://github.com/opencitations/ramose/commit/a27f0d34d9443c410e324dfb38c4dfc664334b04))
* use GET as default SPARQL HTTP method ([c0a101d](https://github.com/opencitations/ramose/commit/c0a101df986ec473d8b534327fa6f619adefde55))


### Features

* add #custom_params field for addon-handled query parameters ([4320f54](https://github.com/opencitations/ramose/commit/4320f54ccb40bb1a6435dd6b28594b89b670ec56)), closes [#custom_params](https://github.com/opencitations/ramose/issues/custom_params)
* add #default_format field to override CSV default per operation ([fffea47](https://github.com/opencitations/ramose/commit/fffea47753486c152777ad07e4e7eb2437e20342)), closes [#default_format](https://github.com/opencitations/ramose/issues/default_format)
* add multi-source SPARQL, SPARQL Anything, OpenAPI export, and pluggable formats ([06fe6da](https://github.com/opencitations/ramose/commit/06fe6da389846ab908edf76643db73c1f3e1e0b5)), closes [opencitations/ramose#20](https://github.com/opencitations/ramose/issues/20)
* expand SKG-IF converter to full product data model ([7094f8c](https://github.com/opencitations/ramose/commit/7094f8c292c28a7339d7d6bf480d6fadc2c210b3))
* **hash_format:** add #disable_params to suppress built-in query parameters ([8c43ffd](https://github.com/opencitations/ramose/commit/8c43ffde76f40ce973f1f8a1ba39c1eeae0517a9)), closes [#disable_params](https://github.com/opencitations/ramose/issues/disable_params) [#disable_params](https://github.com/opencitations/ramose/issues/disable_params)
* **operation:** add result caching and pagination ([3d68769](https://github.com/opencitations/ramose/commit/3d6876985f8d8ffba2f19e176e0eddfd09307c07)), closes [#cache_duration](https://github.com/opencitations/ramose/issues/cache_duration) [#15](https://github.com/opencitations/ramose/issues/15) [#16](https://github.com/opencitations/ramose/issues/16)
* **paging:** pass request URL to format converters for SKG-IF pagination ([dd5a2d9](https://github.com/opencitations/ramose/commit/dd5a2d9f52a83690fec0f2e3f54acd7790554564))
* **skgif:** add citation filters via directive injection into query templates ([5e159cb](https://github.com/opencitations/ramose/commit/5e159cb52e4b3f2ec22ad5d99350e3cc204fc85d)), closes [#sparql](https://github.com/opencitations/ramose/issues/sparql)
* **skgif:** add mock endpoints for missiong entity types and handle empty filters ([0d889c7](https://github.com/opencitations/ramose/commit/0d889c7e9493b93a90942e5f6aea93ef0c1f7d7a))
* **skgif:** add products/{local_identifier} endpoint with JSON-LD output ([86491f7](https://github.com/opencitations/ramose/commit/86491f780f6083f3f22bbf60e2b2debf227ee2f4))
* **skgif:** expand product filter with contributor and type criteria ([f805f4b](https://github.com/opencitations/ramose/commit/f805f4baab1b637ea0266b14672320506598c6d1))

<!--
SPDX-FileCopyrightText: 2026 NONE

SPDX-License-Identifier: CC0-1.0
-->

# [2.0.0](https://github.com/opencitations/ramose/compare/v1.0.6...v2.0.0) (2026-04-03)


* build!: migrate from poetry to uv and update python support ([edc1eca](https://github.com/opencitations/ramose/commit/edc1eca5def8f2e82f88257ad42da717395a6e31))


### Bug Fixes

* **ci:** align uv jobs with matrix python versions ([31d3416](https://github.com/opencitations/ramose/commit/31d3416158b91d9961fdf1ed99cc2e86a50db9b9))
* handle missing ramose.log [release] ([b4a4c9b](https://github.com/opencitations/ramose/commit/b4a4c9b55f0b0f899855da1a3457522ffbc891fa))


### Features

* port oc_api improvements to upstream ramose ([011fd61](https://github.com/opencitations/ramose/commit/011fd616fffc06db34c8114726499909db95ef56))


### BREAKING CHANGES

* minimum Python version raised from 3.7 to 3.10
