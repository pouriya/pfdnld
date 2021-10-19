DOWNLOAD_LINK=https://github.com/pouriya/pfdnld/archive/refs/heads/master.zip
TEST_OUT_DIR=$(CURDIR)/_test/out
TEST_TMP_DIR=$(CURDIR)/_test/tmp
TEST_CFG_DIR=$(CURDIR)/_test/cfg
TEST_LINK_FILE=$(TEST_CFG_DIR)/links.example
TEST_DOWNLOAD_RESULT_FILE=$(TEST_CFG_DIR)/download_result.example
RUN_EXAMPLE_COMMAND=./pfdnld.py --link-file $(TEST_LINK_FILE) --download-result-file $(TEST_DOWNLOAD_RESULT_FILE) --out-dir $(TEST_OUT_DIR) --tmp-dir $(TEST_TMP_DIR)

clean-example:
	@ rm -rf _test

example: clean-example
	@ mkdir _test && mkdir $(TEST_OUT_DIR) && mkdir $(TEST_TMP_DIR) && mkdir $(TEST_CFG_DIR)
	@ echo "$(DOWNLOAD_LINK)" >> $(TEST_LINK_FILE)
	@ echo "$(DOWNLOAD_LINK) a/b/c" >> $(TEST_LINK_FILE)
	@ echo "$(DOWNLOAD_LINK) /foo/bar/baz" >> $(TEST_LINK_FILE)
	@ touch _test/cfg/download_result.example
	@ echo "Created a test directory (_test) with sample configuration files at $(TEST_CFG_DIR)"
	@ echo "Run the following command to test it"
	@ echo "$(RUN_EXAMPLE_COMMAND)"

run-example: example
	$(RUN_EXAMPLE_COMMAND)

install:
	mv pfdnld.py /usr/local/bin/pfdnld

help:
	@ ./pfdnld.py --help
	@ echo
	@ echo "To test it with an example, run make example"
	@ echo "To install it, run [sudo] make install"
