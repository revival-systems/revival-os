# Revival OS: local development entry points. `make help` lists them.
#
# Every target runs on this machine and needs no GitHub service. Each one does
# real work and exits nonzero when that work fails; capabilities that do not
# exist yet have no target (see docs/TESTING.md). CI runs these same targets.

SHELL := bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help
.DELETE_ON_ERROR:
.SECONDARY:
.SUFFIXES:
MAKEFLAGS += --no-builtin-rules

include tools/pins.env

BUILD        ?= build
OUT          := $(abspath $(BUILD))
GOOSE        ?= $(HOME)/.local/share/goose/$(GOOSE_VERSION)/goose
ARM_BIN      ?= $(HOME)/.local/share/revival-os/toolchains/$(ARM_TOOLCHAIN_NAME)/bin
QEMU         ?= qemu-system-arm
PYTHON       ?= python3
HOST_CC      ?= gcc
QEMU_TIMEOUT ?= 20
export GOOSE ARM_BIN QEMU QEMU_TIMEOUT
# Keep the compiler's cache inside the build directory, not ~/.goose.
export GOOSE_HOME := $(OUT)/goose-home

ARM_CC      := $(ARM_BIN)/arm-none-eabi-gcc
ARM_NM      := $(ARM_BIN)/arm-none-eabi-nm
ARM_OBJCOPY := $(ARM_BIN)/arm-none-eabi-objcopy
ARM_OBJDUMP := $(ARM_BIN)/arm-none-eabi-objdump
ARM_READELF := $(ARM_BIN)/arm-none-eabi-readelf

# ARMv7-A, ARM state, software floating point: Krait's FPU and divide
# features are not yet confirmed on the device (docs/hardware/gt-i9195.md).
ARM_ARCH    := -march=armv7-a -marm -mfloat-abi=soft
# Paths in debug information are made machine-independent.
REPRO       := -ffile-prefix-map=$(CURDIR)=. -ffile-prefix-map=$(OUT)=BUILD
ARM_CFLAGS  := $(ARM_ARCH) -std=gnu11 -O2 -g -ffreestanding -fno-builtin -fno-common \
               -ffunction-sections -fdata-sections $(REPRO)
OWN_CFLAGS  := $(ARM_CFLAGS) -Wall -Wextra -Werror
FIXTURE     := tests/qemu/virt-armv7
ARM_LDFLAGS := -nostdlib -T $(FIXTURE)/link.ld -Wl,--gc-sections -Wl,--build-id=none

GEN      := $(OUT)/gen
QEMU_OUT := $(OUT)/qemu-virt-armv7
HOST_OUT := $(OUT)/host
LOGS     := $(OUT)/logs
EXPECT   := tests/expect.sh

PROBE_N        := 1000
PROBE_EXPECT    = $(shell $(PYTHON) -I tests/goose/checksum_oracle.py $(PROBE_N))
PROBE_CASES    := 0 1 2 3
PROBE_ELFS     := $(foreach c,$(PROBE_CASES),$(QEMU_OUT)/probe-$(c).elf)
PROBE_BINS     := $(PROBE_ELFS:.elf=.bin)
# The runtime entry points the probe's Goose-generated C may depend on.
PROBE_SURFACE  := calloc gs_idxfail gs_panic gs_rt_start_$(GOOSE_RUNTIME)
# Boundary tests of the stub's allocator, in an image of their own.
ALLOC_ELF      := $(QEMU_OUT)/alloc.elf
ALLOC_CASES    := 28

SHELL_SCRIPTS := $(wildcard tools/*.sh tests/*.sh tests/*/*.sh)
PY_FILES      := $(wildcard tests/*.py tests/*/*.py)
OWN_C         := $(wildcard $(FIXTURE)/*.c tests/host/*.c)

.PHONY: help doctor install-toolchain build test test-build test-unit test-qemu \
        test-repro lint check-docs check clean qemu-run qemu-debug \
        need-goose need-arm need-qemu

help: ## List the targets
	@echo "Revival OS local development (docs/DEVELOPMENT.md):"
	@grep -hE '^[a-z-]+:.*## ' $(firstword $(MAKEFILE_LIST)) | sed -E 's/:.*## /\t/' | awk -F'\t' '{printf "  make %-18s %s\n", $$1, $$2}'

doctor: ## Check that every required tool is installed and pinned
	@tools/doctor.sh

install-toolchain: ## Install the pinned Goose compiler and Arm toolchain (no sudo)
	tools/install-goose.sh
	tools/install-arm-toolchain.sh

# ---- tool guards: fail with the fix, never skip ---------------------------

need-goose:
	@test -x "$(GOOSE)" || { echo "missing Goose compiler at $(GOOSE): run make install-toolchain"; exit 1; }
need-arm:
	@test -x "$(ARM_CC)" || { echo "missing Arm toolchain at $(ARM_BIN): run make install-toolchain"; exit 1; }
need-qemu:
	@command -v "$(QEMU)" >/dev/null || { echo "missing $(QEMU): sudo apt install qemu-system-arm"; exit 1; }

# ---- generated C -----------------------------------------------------------

# Freestanding form: program C only, linked against the QEMU runtime stub.
$(GEN)/probe.c $(GEN)/probe.h &: tests/goose/probe.goose | need-goose
	@mkdir -p $(GEN)
	$(GOOSE) --header $(GEN)/probe.h -o $(GEN)/probe.c tests/goose/probe.goose >/dev/null

# Hosted form: program and the upstream runtime in one file, for host tests.
$(HOST_OUT)/gen/probe.c $(HOST_OUT)/gen/probe.h &: tests/goose/probe.goose | need-goose
	@mkdir -p $(HOST_OUT)/gen
	$(GOOSE) --standalone --header $(HOST_OUT)/gen/probe.h -o $(HOST_OUT)/gen/probe.c tests/goose/probe.goose >/dev/null

$(GEN)/hosted_probe.c $(GEN)/hosted_probe.h &: tests/goose/hosted_probe.goose | need-goose
	@mkdir -p $(GEN)
	$(GOOSE) --header $(GEN)/hosted_probe.h -o $(GEN)/hosted_probe.c tests/goose/hosted_probe.goose >/dev/null

# ---- ARMv7-A probe images for QEMU virt -----------------------------------

$(QEMU_OUT)/probe.o: $(GEN)/probe.c | need-arm
	@mkdir -p $(@D)
	$(ARM_CC) $(ARM_CFLAGS) -c $< -o $@

$(QEMU_OUT)/hosted_probe.o: $(GEN)/hosted_probe.c | need-arm
	@mkdir -p $(@D)
	$(ARM_CC) $(ARM_CFLAGS) -c $< -o $@

$(QEMU_OUT)/minirt.o: $(FIXTURE)/minirt.c $(FIXTURE)/minirt.h tools/pins.env | need-arm
	@mkdir -p $(@D)
	$(ARM_CC) $(OWN_CFLAGS) -DGOOSE_RUNTIME_ID=$(GOOSE_RUNTIME) -I$(FIXTURE) -c $< -o $@

$(QEMU_OUT)/start.o: $(FIXTURE)/start.S | need-arm
	@mkdir -p $(@D)
	$(ARM_CC) $(ARM_ARCH) -g $(REPRO) -c $< -o $@

$(QEMU_OUT)/main-%.o: $(FIXTURE)/probe_main.c $(FIXTURE)/minirt.h $(GEN)/probe.h tests/goose/checksum_oracle.py | need-arm
	@mkdir -p $(@D)
	$(ARM_CC) $(OWN_CFLAGS) -DPROBE_CASE=$* -DPROBE_N=$(PROBE_N) -DPROBE_EXPECT=$(PROBE_EXPECT) \
	    -I$(GEN) -I$(FIXTURE) -c $< -o $@

$(QEMU_OUT)/probe-%.elf: $(QEMU_OUT)/start.o $(QEMU_OUT)/main-%.o $(QEMU_OUT)/probe.o $(QEMU_OUT)/minirt.o $(FIXTURE)/link.ld
	$(ARM_CC) $(ARM_LDFLAGS) -o $@ $(QEMU_OUT)/start.o $(QEMU_OUT)/main-$*.o \
	    $(QEMU_OUT)/probe.o $(QEMU_OUT)/minirt.o -lgcc

$(QEMU_OUT)/probe-%.bin: $(QEMU_OUT)/probe-%.elf
	$(ARM_OBJCOPY) -O binary $< $@

$(QEMU_OUT)/alloc_main.o: $(FIXTURE)/alloc_main.c $(FIXTURE)/minirt.h | need-arm
	@mkdir -p $(@D)
	$(ARM_CC) $(OWN_CFLAGS) -I$(FIXTURE) -c $< -o $@

$(ALLOC_ELF): $(QEMU_OUT)/start.o $(QEMU_OUT)/alloc_main.o $(QEMU_OUT)/minirt.o $(FIXTURE)/link.ld
	$(ARM_CC) $(ARM_LDFLAGS) -o $@ $(QEMU_OUT)/start.o $(QEMU_OUT)/alloc_main.o $(QEMU_OUT)/minirt.o -lgcc

build: $(PROBE_ELFS) $(PROBE_BINS) $(ALLOC_ELF) ## Build every artifact that exists today (the ARMv7-A probe and allocator test images)
	@cd $(QEMU_OUT) && sha256sum probe-*.elf probe-*.bin alloc.elf

# ---- host build of the probe (hosted Goose runtime) ------------------------

# Generated (upstream runtime) C is compiled without warnings (-w): it is not
# ours to fix. Our driver is compiled with -Werror.
HOST_SAN := -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=undefined

$(HOST_OUT)/probe_gen.o: $(HOST_OUT)/gen/probe.c
	$(HOST_CC) -std=gnu11 -O2 -w -c $< -o $@
$(HOST_OUT)/probe_main.o: tests/host/probe_host_main.c $(HOST_OUT)/gen/probe.h
	$(HOST_CC) -std=gnu11 -O2 -Wall -Wextra -Werror -I$(HOST_OUT)/gen -c $< -o $@
$(HOST_OUT)/probe_host: $(HOST_OUT)/probe_gen.o $(HOST_OUT)/probe_main.o
	$(HOST_CC) $^ -o $@ -lm -pthread

$(HOST_OUT)/probe_gen_asan.o: $(HOST_OUT)/gen/probe.c
	$(HOST_CC) -std=gnu11 -O1 -g -w $(HOST_SAN) -c $< -o $@
$(HOST_OUT)/probe_main_asan.o: tests/host/probe_host_main.c $(HOST_OUT)/gen/probe.h
	$(HOST_CC) -std=gnu11 -O1 -g -Wall -Wextra -Werror $(HOST_SAN) -I$(HOST_OUT)/gen -c $< -o $@
$(HOST_OUT)/probe_host_asan: $(HOST_OUT)/probe_gen_asan.o $(HOST_OUT)/probe_main_asan.o
	$(HOST_CC) $(HOST_SAN) $^ -o $@ -lm -pthread

# ---- tests -----------------------------------------------------------------

test: test-build test-unit test-qemu test-repro ## Run every automated test (build, unit, QEMU, reproducibility)

test-build: build $(QEMU_OUT)/hosted_probe.o ## Check the freestanding build: symbols, ELF attributes, no system calls
	@mkdir -p $(LOGS)
	@got=$$($(ARM_NM) -u $(QEMU_OUT)/probe.o | awk '{print $$2}' | sort | tr '\n' ' ' | sed 's/ $$//'); \
	want=$$(printf '%s\n' $(PROBE_SURFACE) | sort | tr '\n' ' ' | sed 's/ $$//'); \
	if [ "$$got" = "$$want" ]; then echo "PASS build-runtime-surface ($$got)"; \
	else echo "FAIL build-runtime-surface: generated C needs '$$got', expected '$$want'"; exit 1; fi
	@for elf in $(PROBE_ELFS); do \
	  n=$$($(ARM_NM) -u $$elf | wc -l); \
	  [ "$$n" -eq 0 ] || { echo "FAIL build-no-undefined: $$elf has $$n undefined symbols"; exit 1; }; \
	done; echo "PASS build-no-undefined (no C library linked: only the stub and libgcc)"
	@a=$$($(ARM_READELF) -A $(QEMU_OUT)/probe-0.elf); \
	grep -q 'Tag_CPU_arch: v7$$' <<<"$$a" && grep -q 'Tag_CPU_arch_profile: Application' <<<"$$a" \
	  && $(ARM_READELF) -h $(QEMU_OUT)/probe-0.elf | grep -q 'soft-float ABI' \
	  && echo "PASS build-elf-attributes (ARMv7-A, application profile, soft-float EABI)" \
	  || { echo "FAIL build-elf-attributes"; exit 1; }
	@n=$$($(ARM_OBJDUMP) -d $(QEMU_OUT)/probe.o | grep -cE '\s(svc|swi|smc|hvc)\s' || true); \
	[ "$$n" -eq 0 ] && echo "PASS build-no-system-calls (Goose-generated code)" \
	  || { echo "FAIL build-no-system-calls: $$n in $(QEMU_OUT)/probe.o"; exit 1; }
	@$(EXPECT) build-hosted-code-is-rejected nonzero "undefined reference to \`gs_os_clock_ns'" \
	    $(LOGS)/hosted-link.log -- \
	    $(ARM_CC) $(ARM_LDFLAGS) -Wl,-e,probe_clock -o $(QEMU_OUT)/hosted_probe.elf \
	    $(QEMU_OUT)/start.o $(QEMU_OUT)/hosted_probe.o $(QEMU_OUT)/minirt.o -lgcc

test-unit: $(HOST_OUT)/probe_host $(HOST_OUT)/probe_host_asan ## Run host unit tests (Python tools, Goose probe on the host, sanitizers)
	@mkdir -p $(LOGS)
	@$(EXPECT) unit-python 0 "OK" $(LOGS)/unit-python.log -- \
	    $(PYTHON) -I -m unittest discover -s tests -t . -p 'test_*.py'
	@$(EXPECT) unit-host-checksum 0 "$(PROBE_EXPECT)" $(LOGS)/unit-host-checksum.log -- \
	    $(HOST_OUT)/probe_host checksum $(PROBE_N)
	@$(EXPECT) unit-host-index 0 "30" $(LOGS)/unit-host-index.log -- $(HOST_OUT)/probe_host index 2
	@$(EXPECT) unit-host-index-out-of-range nonzero "index 7 out of bounds (length 4)" \
	    $(LOGS)/unit-host-oob.log -- $(HOST_OUT)/probe_host index 7
	@$(EXPECT) unit-sanitized-checksum 0 "$(PROBE_EXPECT)" $(LOGS)/unit-asan-checksum.log -- \
	    $(HOST_OUT)/probe_host_asan checksum $(PROBE_N)
	@$(EXPECT) unit-sanitized-index 0 "30" $(LOGS)/unit-asan-index.log -- $(HOST_OUT)/probe_host_asan index 2

test-qemu: build | need-qemu ## Boot the probe and allocator test images in QEMU (ARMv7-A virt): results and failure paths
	@mkdir -p $(LOGS)
	@tests/qemu/run.sh qemu-checksum $(QEMU_OUT)/probe-0.elf $(LOGS)/qemu-0.log 0 \
	    "probe: probe_checksum($(PROBE_N)) = $(PROBE_EXPECT)"
	@tests/qemu/run.sh qemu-index-out-of-range $(QEMU_OUT)/probe-1.elf $(LOGS)/qemu-1.log 1 \
	    "panic: index out of range: 7 not in [0, 4)"
	@QEMU_TIMEOUT=3 tests/qemu/run.sh qemu-hang-is-stopped $(QEMU_OUT)/probe-2.elf $(LOGS)/qemu-2.log \
	    timeout "probe: hanging on purpose"
	@tests/qemu/run.sh qemu-undefined-instruction $(QEMU_OUT)/probe-3.elf $(LOGS)/qemu-3.log 1 \
	    "probe: unexpected exception, vector 1"
	@tests/qemu/run.sh qemu-alloc-bounds $(ALLOC_ELF) $(LOGS)/qemu-alloc.log 0 \
	    "alloc: PASS ($(ALLOC_CASES) of $(ALLOC_CASES) cases)"

test-repro: ## Build twice from scratch in separate directories and require identical outputs
	@rm -rf $(OUT)/repro-a $(OUT)/repro-b
	@$(MAKE) --no-print-directory -s BUILD=$(OUT)/repro-a build >/dev/null
	@$(MAKE) --no-print-directory -s BUILD=$(OUT)/repro-b build >/dev/null
	@cd $(OUT)/repro-a && find gen qemu-virt-armv7 -type f \( -name '*.c' -o -name '*.h' -o -name '*.elf' -o -name '*.bin' \) \
	    | sort | xargs sha256sum > ../repro-a.sha256
	@cd $(OUT)/repro-b && sha256sum --quiet -c ../repro-a.sha256 \
	    && echo "PASS repro-identical ($$(wc -l < ../repro-a.sha256) files byte-identical across two clean builds)" \
	    || { echo "FAIL repro-identical: see $(OUT)/repro-a.sha256"; exit 1; }

# ---- static checks ---------------------------------------------------------

lint: $(GEN)/probe.h ## Static analysis: shellcheck, cppcheck, Python syntax
	@command -v shellcheck >/dev/null || { echo "missing shellcheck: sudo apt install shellcheck"; exit 1; }
	@command -v cppcheck >/dev/null || { echo "missing cppcheck: sudo apt install cppcheck"; exit 1; }
	@shellcheck -x $(SHELL_SCRIPTS) && echo "PASS lint-shellcheck ($(words $(SHELL_SCRIPTS)) scripts)"
	@cppcheck --quiet --error-exitcode=1 --std=c11 --enable=warning,style,performance,portability \
	    --inline-suppr --suppress=missingIncludeSystem -DGOOSE_RUNTIME_ID=0 -DPROBE_CASE=0 -DPROBE_N=1 -DPROBE_EXPECT=0 \
	    -I$(FIXTURE) -I$(GEN) $(OWN_C) && echo "PASS lint-cppcheck ($(words $(OWN_C)) C files)"
	@$(PYTHON) -I -m py_compile $(PY_FILES) && echo "PASS lint-python ($(words $(PY_FILES)) files compile)"

check-docs: ## Check documentation links, anchors and the roadmap's phase template
	@$(PYTHON) -I tests/docs/check_docs.py

check: doctor lint check-docs test ## Everything to run before pushing: tools, lint, docs, all tests

clean: ## Remove the build directory (sources are never touched)
	@case "$(OUT)" in "$(CURDIR)"|"$(HOME)"|/|"") echo "refusing to remove '$(OUT)'"; exit 1;; esac
	rm -rf $(OUT)

# ---- interactive (not tests) ----------------------------------------------

qemu-run: $(QEMU_OUT)/probe-0.elf | need-qemu ## Run the checksum probe in QEMU interactively (Ctrl-A X quits)
	$(QEMU) -M virt -cpu cortex-a15 -m 64M -nographic -semihosting-config enable=on,target=native -kernel $<

qemu-debug: $(QEMU_OUT)/probe-0.elf | need-qemu ## Start QEMU halted with a GDB server on port 1234
	@echo "In another terminal: gdb-multiarch $< -ex 'target remote :1234'"
	$(QEMU) -M virt -cpu cortex-a15 -m 64M -nographic -semihosting-config enable=on,target=native -s -S -kernel $<
