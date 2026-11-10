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
# The target flags select libgcc's ARMv7-A build, the one the code is compiled for.
ARM_LDFLAGS := $(ARM_ARCH) -nostdlib -T $(FIXTURE)/link.ld -Wl,--gc-sections -Wl,--build-id=none

# Rust bare-metal toolchain (Phase 1+, ADR 0001), pinned in tools/pins.env and
# rust-toolchain.toml and installed isolated by tools/install-rust.sh.
RUST_PREFIX ?= $(HOME)/.local/share/revival-os
export RUSTUP_HOME := $(RUST_PREFIX)/rustup
export CARGO_HOME  := $(RUST_PREFIX)/cargo
RUSTC       ?= $(CARGO_HOME)/bin/rustc
# A no_std ARMv7-A binary. rustc links its own core and compiler_builtins; the
# Arm GNU linker (bfd) is only the backend, and no C library or -lgcc is added.
RUST_FLAGS  := --target $(RUST_TARGET) --edition 2021 --crate-type bin \
               -C panic=abort -C opt-level=2 -C relocation-model=static \
               -D warnings --remap-path-prefix $(CURDIR)=.
# Common link flags; each image appends its own linker script (-T). Phase 1
# uses the QEMU fixture's link.ld (RAM 0x40000000); the Phase 2 payload uses
# the device link.ld (load 0x80208000). Splitting the script out does not
# change the Phase 1 expansion of RUST_LINK.
RUST_LINK_BASE := -C linker=$(ARM_CC) -C linker-flavor=gcc -C link-arg=-fuse-ld=bfd \
               -C link-arg=-nostartfiles -C link-arg=-nostdlib \
               -C link-arg=-Wl,--gc-sections -C link-arg=-Wl,--build-id=none
RUST_LINK   := $(RUST_LINK_BASE) -C link-arg=-Wl,-T,$(FIXTURE)/link.ld

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
# Phase 1 Rust kernel images: the heartbeat (normal) plus two negative-test
# builds selected by a cfg, mirroring the probe's PROBE_CASE.
KERNEL_MODES   := heartbeat panic oob
KERNEL_ELFS    := $(foreach m,$(KERNEL_MODES),$(QEMU_OUT)/kernel-$(m).elf)
# Phase 1 Rust negative-test artifacts (hosted-dependency rejection and
# corrupted-image detection). Built only by test-rust, never by `build`, and
# kept out of the reproducibility set.
RUSTNEG        := $(OUT)/rust-negative

# Phase 2 GT-I9195 proof-of-execution payload (the device image, boot/ layer per
# ARCHITECTURE.md). Built here and tested only in QEMU; never flashed.
PAYLOAD_DIR  := boot/samsung-serranolte
PAYLOAD_OUT  := $(OUT)/boot-serrano
PAYLOAD_ELF  := $(PAYLOAD_OUT)/payload.elf
PAYLOAD_BIN  := $(PAYLOAD_OUT)/payload.bin
PAYLOAD_IMG  := $(PAYLOAD_OUT)/payload.img
RUST_PAYLOAD_LINK := $(RUST_LINK_BASE) -C link-arg=-Wl,-T,$(PAYLOAD_DIR)/link.ld

SHELL_SCRIPTS := $(wildcard tools/*.sh tests/*.sh tests/*/*.sh)
PY_FILES      := $(wildcard tests/*.py tests/*/*.py tools/*.py)
OWN_C         := $(wildcard $(FIXTURE)/*.c tests/host/*.c tests/build/link-negative/*.c)

.PHONY: help doctor install-toolchain build payload test test-build test-unit test-qemu \
        test-rust test-payload test-repro lint check-docs check clean qemu-run qemu-debug \
        need-goose need-arm need-qemu need-rust

help: ## List the targets
	@echo "Revival OS local development (docs/DEVELOPMENT.md):"
	@grep -hE '^[a-z-]+:.*## ' $(firstword $(MAKEFILE_LIST)) | sed -E 's/:.*## /\t/' | awk -F'\t' '{printf "  make %-18s %s\n", $$1, $$2}'

doctor: ## Check that every required tool is installed and pinned
	@tools/doctor.sh

install-toolchain: ## Install the pinned Goose compiler, Arm toolchain and Rust (no sudo)
	tools/install-goose.sh
	tools/install-arm-toolchain.sh
	tools/install-rust.sh

# ---- tool guards: fail with the fix, never skip ---------------------------

need-goose:
	@test -x "$(GOOSE)" || { echo "missing Goose compiler at $(GOOSE): run make install-toolchain"; exit 1; }
need-arm:
	@test -x "$(ARM_CC)" || { echo "missing Arm toolchain at $(ARM_BIN): run make install-toolchain"; exit 1; }
need-qemu:
	@command -v "$(QEMU)" >/dev/null || { echo "missing $(QEMU): sudo apt install qemu-system-arm"; exit 1; }
need-rust:
	@test -x "$(RUSTC)" || { echo "missing Rust at $(RUSTC): run make install-toolchain (tools/install-rust.sh)"; exit 1; }

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

# Each link also writes its map, which build-link-map checks.
$(QEMU_OUT)/probe-%.elf $(QEMU_OUT)/probe-%.map: $(QEMU_OUT)/start.o $(QEMU_OUT)/main-%.o $(QEMU_OUT)/probe.o $(QEMU_OUT)/minirt.o $(FIXTURE)/link.ld
	$(ARM_CC) $(ARM_LDFLAGS) -Wl,-Map=$(QEMU_OUT)/probe-$*.map -o $(QEMU_OUT)/probe-$*.elf \
	    $(QEMU_OUT)/start.o $(QEMU_OUT)/main-$*.o $(QEMU_OUT)/probe.o $(QEMU_OUT)/minirt.o -lgcc

$(QEMU_OUT)/probe-%.bin: $(QEMU_OUT)/probe-%.elf
	$(ARM_OBJCOPY) -O binary $< $@

$(QEMU_OUT)/alloc_main.o: $(FIXTURE)/alloc_main.c $(FIXTURE)/minirt.h | need-arm
	@mkdir -p $(@D)
	$(ARM_CC) $(OWN_CFLAGS) -I$(FIXTURE) -c $< -o $@

$(ALLOC_ELF) $(ALLOC_ELF:.elf=.map) &: $(QEMU_OUT)/start.o $(QEMU_OUT)/alloc_main.o $(QEMU_OUT)/minirt.o $(FIXTURE)/link.ld
	$(ARM_CC) $(ARM_LDFLAGS) -Wl,-Map=$(ALLOC_ELF:.elf=.map) -o $(ALLOC_ELF) \
	    $(QEMU_OUT)/start.o $(QEMU_OUT)/alloc_main.o $(QEMU_OUT)/minirt.o -lgcc

# ---- Phase 1 Rust kernel images for QEMU virt -----------------------------

# The ARM entry stub: sets the stack, zeroes .bss, calls Rust kmain, and holds
# the one documented semihosting-exit svc. Assembled, not Rust (ADR 0001).
$(QEMU_OUT)/kstart.o: $(FIXTURE)/kstart.S | need-arm
	@mkdir -p $(@D)
	$(ARM_CC) $(ARM_ARCH) -g $(REPRO) -c $< -o $@

# rustc drives the link (its own core + compiler_builtins); the Arm GNU linker
# is the backend via -fuse-ld=bfd; kstart.o supplies _start and the exit. The
# mode stem selects the image: heartbeat (none), panic, or oob.
$(QEMU_OUT)/kernel-%.elf: $(FIXTURE)/kernel.rs $(QEMU_OUT)/kstart.o $(FIXTURE)/link.ld | need-rust need-arm
	@mkdir -p $(@D)
	cfg=; case '$*' in panic) cfg='--cfg kmode_panic';; oob) cfg='--cfg kmode_oob';; esac; \
	$(RUSTC) $(RUST_FLAGS) $(RUST_LINK) -C link-arg=$(QEMU_OUT)/kstart.o $$cfg \
	    --emit link -o $@ $(FIXTURE)/kernel.rs

# ---- Phase 2 GT-I9195 proof-of-execution payload (device image) -----------

# The device entry stub (ARM asm): zImage header, handoff capture, mask IRQ/FIQ,
# stack, zero .bss, call Rust, then a masked wfi halt. NO svc in the image.
$(PAYLOAD_OUT)/kstart.o: $(PAYLOAD_DIR)/kstart.S | need-arm
	@mkdir -p $(@D)
	$(ARM_CC) $(ARM_ARCH) -g $(REPRO) -c $< -o $@

# rustc drives the link (its own core + compiler_builtins), bfd backend, device
# link.ld (load 0x80208000); kstart.o supplies _start. No C library, no -lgcc.
$(PAYLOAD_ELF): $(PAYLOAD_DIR)/payload.rs $(PAYLOAD_OUT)/kstart.o $(PAYLOAD_DIR)/link.ld | need-rust need-arm
	@mkdir -p $(@D)
	$(RUSTC) $(RUST_FLAGS) $(RUST_PAYLOAD_LINK) -C link-arg=$(PAYLOAD_OUT)/kstart.o \
	    --emit link -o $@ $(PAYLOAD_DIR)/payload.rs

# The exact kernel-slot bytes the stock bootloader would run (flat binary).
$(PAYLOAD_BIN): $(PAYLOAD_ELF)
	$(ARM_OBJCOPY) -O binary $< $@

# The shippable Android boot image v0 (not flashed by any target).
$(PAYLOAD_IMG): $(PAYLOAD_BIN) tools/pack_bootimg.py
	$(PYTHON) -I tools/pack_bootimg.py --kernel $< --output $@

payload: $(PAYLOAD_BIN) $(PAYLOAD_IMG) ## Build the Phase 2 payload (.bin kernel slot + .img boot image)

build: $(PROBE_ELFS) $(PROBE_BINS) $(ALLOC_ELF) $(KERNEL_ELFS) $(PAYLOAD_BIN) $(PAYLOAD_IMG) ## Build every artifact that exists today (the ARMv7-A probe, allocator, Rust kernel and Phase 2 payload images)
	@cd $(QEMU_OUT) && sha256sum probe-*.elf probe-*.bin alloc.elf kernel-*.elf
	@cd $(PAYLOAD_OUT) && sha256sum payload.elf payload.bin payload.img

# ---- link check (build-link-map) -------------------------------------------

# libgcc members an image may contain, each listed with the reason it is
# needed. None today. Any other member fails build-link-map until reviewed.
LIBGCC_APPROVED :=
LIBGCC     = $(shell $(ARM_CC) $(ARM_LDFLAGS) -print-libgcc-file-name)
CHECK_LINK = $(PYTHON) -I tests/build/check_link.py --nm $(ARM_NM) --libgcc $(LIBGCC) \
             $(addprefix --approve ,$(LIBGCC_APPROVED))

# Deliberately bad links that the check must reject: the probe-0 inputs plus
# one object from tests/build/link-negative/, kept with -u neg_entry.
LINKNEG       := $(OUT)/link-negative
LINKNEG_CASES := c_library libgcc_helper weak_unresolved strong_unresolved extra_object
LINKNEG_BASE  := $(QEMU_OUT)/start.o $(QEMU_OUT)/main-0.o $(QEMU_OUT)/probe.o $(QEMU_OUT)/minirt.o
LINKNEG_LIBS_c_library          := -lc
LINKNEG_FLAGS_strong_unresolved := -Wl,--unresolved-symbols=ignore-all
# Everything build-link-map reads: the images' maps and the bad links.
LINK_CHECKED  := $(PROBE_ELFS:.elf=.map) $(ALLOC_ELF:.elf=.map) \
                 $(LINKNEG_CASES:%=$(LINKNEG)/%.elf) $(LINKNEG_CASES:%=$(LINKNEG)/%.map)

$(LINKNEG)/%.o: tests/build/link-negative/%.c | need-arm
	@mkdir -p $(@D)
	$(ARM_CC) $(OWN_CFLAGS) -c $< -o $@

$(LINKNEG)/%.elf $(LINKNEG)/%.map: $(LINKNEG)/%.o $(LINKNEG_BASE) $(FIXTURE)/link.ld
	$(ARM_CC) $(ARM_LDFLAGS) $(LINKNEG_FLAGS_$*) -Wl,-u,neg_entry -Wl,-Map=$(LINKNEG)/$*.map \
	    -o $(LINKNEG)/$*.elf $(LINKNEG_BASE) $< $(LINKNEG_LIBS_$*) -lgcc

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

test: test-build test-unit test-qemu test-rust test-payload test-repro ## Run every automated test (build, unit, QEMU, Rust kernel, Phase 2 payload, reproducibility)

test-build: build $(QEMU_OUT)/hosted_probe.o $(LINK_CHECKED) ## Check the freestanding build: link inputs, symbols, ELF attributes, no system calls
	@mkdir -p $(LOGS)
	@got=$$($(ARM_NM) -u $(QEMU_OUT)/probe.o | awk '{print $$2}' | sort | tr '\n' ' ' | sed 's/ $$//'); \
	want=$$(printf '%s\n' $(PROBE_SURFACE) | sort | tr '\n' ' ' | sed 's/ $$//'); \
	if [ "$$got" = "$$want" ]; then echo "PASS build-runtime-surface ($$got)"; \
	else echo "FAIL build-runtime-surface: generated C needs '$$got', expected '$$want'"; exit 1; fi
	@for c in $(PROBE_CASES); do \
	  $(CHECK_LINK) --map $(QEMU_OUT)/probe-$$c.map --elf $(QEMU_OUT)/probe-$$c.elf \
	      $(QEMU_OUT)/start.o $(QEMU_OUT)/main-$$c.o $(QEMU_OUT)/probe.o $(QEMU_OUT)/minirt.o \
	    || { echo "FAIL build-link-map: probe-$$c.elf"; exit 1; }; \
	done; \
	$(CHECK_LINK) --map $(QEMU_OUT)/alloc.map --elf $(ALLOC_ELF) \
	    $(QEMU_OUT)/start.o $(QEMU_OUT)/alloc_main.o $(QEMU_OUT)/minirt.o \
	  || { echo "FAIL build-link-map: alloc.elf"; exit 1; }; \
	echo "PASS build-link-map ($(words $(PROBE_ELFS) $(ALLOC_ELF)) images: only their own objects, no C library," \
	     "no libgcc member that is not approved, every reference resolved)"
	@$(EXPECT) build-link-map-rejects-c-library nonzero "archive member not approved: libc.a(libc_a-strlen.o)" \
	    $(LOGS)/link-neg-c_library.log -- $(CHECK_LINK) --map $(LINKNEG)/c_library.map \
	    --elf $(LINKNEG)/c_library.elf $(LINKNEG_BASE) $(LINKNEG)/c_library.o
	@$(EXPECT) build-link-map-rejects-unapproved-libgcc nonzero "libgcc member not approved: _aeabi_uldivmod.o" \
	    $(LOGS)/link-neg-libgcc_helper.log -- $(CHECK_LINK) --map $(LINKNEG)/libgcc_helper.map \
	    --elf $(LINKNEG)/libgcc_helper.elf $(LINKNEG_BASE) $(LINKNEG)/libgcc_helper.o
	@$(EXPECT) build-link-map-rejects-weak-unresolved nonzero "unresolved weak reference to neg_missing" \
	    $(LOGS)/link-neg-weak_unresolved.log -- $(CHECK_LINK) --map $(LINKNEG)/weak_unresolved.map \
	    --elf $(LINKNEG)/weak_unresolved.elf $(LINKNEG_BASE) $(LINKNEG)/weak_unresolved.o
	@$(EXPECT) build-link-map-rejects-ignored-unresolved nonzero "unresolved reference to neg_missing" \
	    $(LOGS)/link-neg-strong_unresolved.log -- $(CHECK_LINK) --map $(LINKNEG)/strong_unresolved.map \
	    --elf $(LINKNEG)/strong_unresolved.elf $(LINKNEG_BASE) $(LINKNEG)/strong_unresolved.o
	@$(EXPECT) build-link-map-rejects-unexpected-object nonzero "unexpected input object: extra_object.o" \
	    $(LOGS)/link-neg-extra_object.log -- $(CHECK_LINK) --map $(LINKNEG)/extra_object.map \
	    --elf $(LINKNEG)/extra_object.elf $(LINKNEG_BASE)
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

test-rust: $(KERNEL_ELFS) $(FIXTURE)/hosted_std.rs $(FIXTURE)/hosted_libc.rs tests/build/check_image_integrity.sh | need-qemu need-arm need-rust ## Boot the Phase 1 Rust kernel images, check build attributes, and reject hosted deps and corrupted images
	@mkdir -p $(LOGS)
	@tests/qemu/run.sh qemu-rust-heartbeat $(QEMU_OUT)/kernel-heartbeat.elf $(LOGS)/krt-heartbeat.log 0 \
	    "revival-os: phase 1 rust heartbeat"
	@tests/qemu/run.sh qemu-rust-panic $(QEMU_OUT)/kernel-panic.elf $(LOGS)/krt-panic.log 1 "panic:"
	@tests/qemu/run.sh qemu-rust-bounds $(QEMU_OUT)/kernel-oob.elf $(LOGS)/krt-bounds.log 1 "panic:"
	@u=$$($(ARM_NM) -u $(QEMU_OUT)/kernel-heartbeat.elf | wc -l | tr -d ' '); \
	  if [ "$$u" = 0 ]; then echo "PASS build-rust-symbols (no undefined symbols; Rust links its own core)"; \
	  else echo "FAIL build-rust-symbols: $$u undefined"; $(ARM_NM) -u $(QEMU_OUT)/kernel-heartbeat.elf; exit 1; fi
	@n=$$($(ARM_OBJDUMP) -d $(QEMU_OUT)/kernel-heartbeat.elf | grep -cE '\s(svc|swi|smc|hvc)\s' || true); \
	  if [ "$$n" = 1 ]; then echo "PASS build-rust-one-svc (only the documented semihosting exit)"; \
	  else echo "FAIL build-rust-one-svc: found $$n"; exit 1; fi
	@a=$$($(ARM_READELF) -A $(QEMU_OUT)/kernel-heartbeat.elf); \
	  grep -q 'Tag_CPU_arch: v7$$' <<<"$$a" && grep -q 'Tag_CPU_arch_profile: Application' <<<"$$a" \
	  && $(ARM_READELF) -h $(QEMU_OUT)/kernel-heartbeat.elf | grep -q 'soft-float ABI' \
	  && echo "PASS build-rust-elf-attributes (ARMv7-A, Application, soft-float EABI)" \
	  || { echo "FAIL build-rust-elf-attributes"; exit 1; }
	@mkdir -p $(RUSTNEG)
	@$(EXPECT) build-rust-rejects-std nonzero "may not support the standard library" \
	    $(LOGS)/krt-neg-std.log -- \
	    $(RUSTC) $(RUST_FLAGS) $(RUST_LINK) -C link-arg=$(QEMU_OUT)/kstart.o \
	    --emit link -o $(RUSTNEG)/kernel-hosted-std.elf $(FIXTURE)/hosted_std.rs
	@$(RUSTC) $(RUST_FLAGS) --emit obj -o $(RUSTNEG)/hosted_libc.o $(FIXTURE)/hosted_libc.rs 2>$(LOGS)/krt-neg-libc-obj.log \
	  && echo "PASS build-rust-hosted-libc-compiles (valid no_std fixture; the link failure below is the libc symbol, not a compile error)" \
	  || { echo "FAIL build-rust-hosted-libc-compiles (see $(LOGS)/krt-neg-libc-obj.log)"; exit 1; }
	@$(EXPECT) build-rust-rejects-libc nonzero "undefined reference to \`puts'" \
	    $(LOGS)/krt-neg-libc.log -- \
	    $(RUSTC) $(RUST_FLAGS) $(RUST_LINK) -C link-arg=$(QEMU_OUT)/kstart.o \
	    --emit link -o $(RUSTNEG)/kernel-hosted-libc.elf $(FIXTURE)/hosted_libc.rs
	@tests/build/check_image_integrity.sh $(QEMU_OUT)/kernel-heartbeat.elf $(RUSTNEG)

test-payload: $(PAYLOAD_BIN) $(PAYLOAD_IMG) $(PAYLOAD_OUT)/kstart.o tests/boot/run_payload.py tests/boot/read_bootimg.py tests/boot/serrano_v1.py tests/boot/payload_hosted_libc.rs $(FIXTURE)/hosted_std.rs tests/build/check_image_integrity.sh | need-qemu need-arm need-rust ## Boot the Phase 2 payload in QEMU (paint both framebuffers), and check the handoff, the packer and reproducibility
	@mkdir -p $(LOGS) $(PAYLOAD_OUT)/neg
	@echo "# (a) run the exact kernel-slot bytes; both framebuffers must match the host oracle"
	@halt=$$($(ARM_NM) $(PAYLOAD_ELF) | awk '$$3=="halt_loop"{print $$1}'); \
	  test -n "$$halt" || { echo "FAIL qemu-payload: no halt_loop symbol in $(PAYLOAD_ELF)"; exit 1; }; \
	  $(PYTHON) -m tests.boot.run_payload --payload $(PAYLOAD_BIN) --workdir $(PAYLOAD_OUT)/qemu --halt-addr 0x$$halt
	@echo "# (b) build/negative checks on the payload image"
	@n=$$($(ARM_OBJDUMP) -d $(PAYLOAD_ELF) | grep -cE '\s(svc|swi|smc|hvc)\s' || true); \
	  if [ "$$n" = 0 ]; then echo "PASS payload-no-system-calls (zero svc/swi/smc/hvc)"; \
	  else echo "FAIL payload-no-system-calls: found $$n"; exit 1; fi
	@u=$$($(ARM_NM) -u $(PAYLOAD_ELF) | wc -l | tr -d ' '); \
	  if [ "$$u" = 0 ]; then echo "PASS payload-symbols (no undefined symbols; Rust links its own core)"; \
	  else echo "FAIL payload-symbols: $$u undefined"; $(ARM_NM) -u $(PAYLOAD_ELF); exit 1; fi
	@a=$$($(ARM_READELF) -A $(PAYLOAD_ELF)); \
	  grep -q 'Tag_CPU_arch: v7$$' <<<"$$a" && grep -q 'Tag_CPU_arch_profile: Application' <<<"$$a" \
	  && $(ARM_READELF) -h $(PAYLOAD_ELF) | grep -q 'soft-float ABI' \
	  && echo "PASS payload-elf-attributes (ARMv7-A, Application, soft-float EABI)" \
	  || { echo "FAIL payload-elf-attributes"; exit 1; }
	@$(EXPECT) payload-rejects-std nonzero "may not support the standard library" \
	    $(LOGS)/payload-neg-std.log -- \
	    $(RUSTC) $(RUST_FLAGS) $(RUST_PAYLOAD_LINK) -C link-arg=$(PAYLOAD_OUT)/kstart.o \
	    --emit link -o $(PAYLOAD_OUT)/neg/payload-std.elf $(FIXTURE)/hosted_std.rs
	@$(EXPECT) payload-rejects-libc nonzero "undefined reference to \`puts'" \
	    $(LOGS)/payload-neg-libc.log -- \
	    $(RUSTC) $(RUST_FLAGS) $(RUST_PAYLOAD_LINK) -C link-arg=$(PAYLOAD_OUT)/kstart.o \
	    --emit link -o $(PAYLOAD_OUT)/neg/payload-libc.elf tests/boot/payload_hosted_libc.rs
	@tests/build/check_image_integrity.sh $(PAYLOAD_BIN) $(PAYLOAD_OUT)/neg payload
	@echo "# (c) packer: an independent reader validates every boot-image field"
	@$(EXPECT) payload-bootimg-valid 0 "OK" $(LOGS)/payload-read.log -- \
	    $(PYTHON) -m tests.boot.read_bootimg $(PAYLOAD_IMG)
	@echo "# (d) reproducibility: two clean builds give byte-identical .bin and .img"
	@rm -rf $(OUT)/payload-repro-a $(OUT)/payload-repro-b
	@$(MAKE) --no-print-directory -s BUILD=$(OUT)/payload-repro-a payload >/dev/null
	@$(MAKE) --no-print-directory -s BUILD=$(OUT)/payload-repro-b payload >/dev/null
	@if cmp -s $(OUT)/payload-repro-a/boot-serrano/payload.bin $(OUT)/payload-repro-b/boot-serrano/payload.bin \
	    && cmp -s $(OUT)/payload-repro-a/boot-serrano/payload.img $(OUT)/payload-repro-b/boot-serrano/payload.img; then \
	  echo "PASS payload-repro-identical (payload.bin and payload.img byte-identical across two clean builds)"; \
	else echo "FAIL payload-repro-identical"; exit 1; fi

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
	$(QEMU) -M virt -cpu cortex-a15 -m 64M -nic none -nographic -semihosting-config enable=on,target=native -kernel $<

qemu-debug: $(QEMU_OUT)/probe-0.elf | need-qemu ## Start QEMU halted with a GDB server on port 1234
	@echo "In another terminal: gdb-multiarch $< -ex 'target remote :1234'"
	$(QEMU) -M virt -cpu cortex-a15 -m 64M -nic none -nographic -semihosting-config enable=on,target=native -s -S -kernel $<
