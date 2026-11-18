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
# Emulator-only task experiment (ADR 0003): stackful tasks, a cooperative
# context switch and a guard word per stack, next to the Phase 1 fixture.
# QEMU fixture, not OS code. One image per case. TASKS_CFG_<case> gives the
# case, the task-table capacity, the bytes per stack, the yields per task (or
# steps per job) and, for the job cases, the jobs; tasks.rs reads them with
# env!(). The job cases (the second experiment, run-to-completion jobs on a
# bounded queue) run every job on one runner task. The async cases (the third,
# stackless tasks) give the pool's capacity in the jobs field and its slot
# bytes after it, and run every task's state machine on one executor task.
# tests/qemu/measure_tasks.sh builds more cases through the same rule.
TASKS_LD                := $(FIXTURE)/tasks.ld
TASKS_CASES             := many-1k many-10k full overflow overflow-sp overflow-exit overflow-moat return registers \
                           jobs-1k jobs-100k jobs-full jobs-overflow async-1k async-100k async-full async-overflow
TASKS_ELFS              := $(TASKS_CASES:%=$(QEMU_OUT)/tasks-%.elf)
TASKS_CFG_many-1k       := many 1000 512 100
TASKS_CFG_many-10k      := many 10000 256 10
TASKS_CFG_full          := full 64 256 3
TASKS_CFG_overflow      := overflow 4 512 4
TASKS_CFG_overflow-sp   := overflow_sp 4 512 4
TASKS_CFG_overflow-exit := overflow_exit 4 512 4
TASKS_CFG_overflow-moat := overflow_moat 4 512 4
TASKS_CFG_return        := return 64 256 1
TASKS_CFG_registers     := registers 64 256 50
TASKS_CFG_jobs-1k       := jobs_many 4 512 100 1000
TASKS_CFG_jobs-100k     := jobs_many 4 512 10 100000
TASKS_CFG_jobs-full     := jobs_full 4 512 3 64
TASKS_CFG_jobs-overflow := jobs_overflow 4 512 1 3
TASKS_CFG_async-1k       := async_many 4 512 100 1000 16
TASKS_CFG_async-100k     := async_many 4 512 10 100000 16
TASKS_CFG_async-full     := async_full 4 512 3 64 16
TASKS_CFG_async-overflow := async_overflow 4 512 1 3 16
# Emulator-only exception reporting (a step toward ROADMAP 3a): vectors that
# say which exception happened and where, then halt. One image per case.
EXC_CASES := undef dabt pabt
EXC_ELFS  := $(EXC_CASES:%=$(QEMU_OUT)/exc-%.elf)

# Phase 2 GT-I9195 proof-of-execution payload (the device image, boot/ layer per
# ARCHITECTURE.md). Built here and tested only in QEMU; never flashed.
PAYLOAD_DIR  := boot/samsung-serranolte
PAYLOAD_OUT  := $(OUT)/boot-serrano
PAYLOAD_ELF  := $(PAYLOAD_OUT)/payload.elf
PAYLOAD_BIN  := $(PAYLOAD_OUT)/payload.bin
PAYLOAD_IMG  := $(PAYLOAD_OUT)/payload.img
# The Phase 2 NEGATIVE-TEST image (ROADMAP Phase 2, "a deliberately invalid
# image (bad header)"): payload.img with the magic "INVALID!" and nothing else
# changed. Built by `make payload-invalid` and by test-payload, never by
# `build` or `payload`, so those print the real image's hashes only.
PAYLOAD_INVALID_IMG := $(PAYLOAD_OUT)/payload-invalid.img
# The payload is FROZEN at the reviewed v1.3 bytes (PR #10, commit be485e2).
# test-payload fails if either hash changes; a new payload needs a new review,
# and these two lines change in that same reviewed pull request.
PAYLOAD_BIN_SHA256 := 8ee519ae31a9d005f72e14e21ff5c0b7baadefbec225083013820d5700616a2b
PAYLOAD_IMG_SHA256 := bde09074c1e7f48ac04be318bba9905228fc26ad077e94ab9ded5dc00bb1ce02
RUST_PAYLOAD_LINK := $(RUST_LINK_BASE) -C link-arg=-Wl,-T,$(PAYLOAD_DIR)/link.ld

# Phase 2 image 2: the text console (docs/phase-2/console-payload.md). Its Rust
# is in $(CONSOLE_DIR). It is entered through the first image's kstart.S and
# laid out by its link.ld, both used unchanged (the same kstart.o). It has its
# own output directory, so build/boot-serrano/ holds the first image only.
# Built here and tested only in QEMU; no target flashes it.
CONSOLE_DIR  := $(PAYLOAD_DIR)/console
CONSOLE_OUT  := $(OUT)/boot-serrano-console
CONSOLE_ELF  := $(CONSOLE_OUT)/console.elf
CONSOLE_BIN  := $(CONSOLE_OUT)/console.bin
CONSOLE_IMG  := $(CONSOLE_OUT)/console.img
CONSOLE_SRC  := $(wildcard $(CONSOLE_DIR)/*.rs)
# Optimisation level of the console image: z, the smallest. At level 2 the
# flat image is over CONSOLE_MAX_BYTES (12,412 bytes at fd9ad49; z gave 6,000).
# `make console-sizes` compares 2, s and z. The level is part of the image:
# the stamp file below makes a build with another level rebuild it.
CONSOLE_OPT  ?= z
CONSOLE_MAX_BYTES := 8192
CONSOLE_OPT_STAMP := $(CONSOLE_OUT)/opt-level-$(CONSOLE_OPT).stamp
# The console image's reviewed bytes. Empty until a build of it has been
# reviewed; then test console-frozen fails if either hash changes, as
# payload-frozen does for the first image.
CONSOLE_BIN_SHA256 :=
CONSOLE_IMG_SHA256 :=
# The console's board-independent modules, built for this machine with their
# host tests (tests/boot/console_host.rs).
CONSOLE_HOST_TESTS := $(CONSOLE_OUT)/console-host-tests

SHELL_SCRIPTS := $(wildcard tools/*.sh tests/*.sh tests/*/*.sh)
PY_FILES      := $(wildcard tests/*.py tests/*/*.py tools/*.py)
OWN_C         := $(wildcard $(FIXTURE)/*.c tests/host/*.c tests/build/link-negative/*.c)

.PHONY: help doctor install-toolchain build payload payload-invalid test test-build test-unit test-qemu \
        test-rust test-tasks test-exceptions test-payload test-repro lint check-docs check clean qemu-run qemu-debug \
        measure-tasks need-goose need-arm need-qemu need-rust console console-sizes console-sample test-console

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

# ---- emulator-only task experiment (ADR 0003) ------------------------------

# The context switch, the experiment's only assembly (switch.S says why).
$(QEMU_OUT)/switch.o: $(FIXTURE)/switch.S | need-arm
	@mkdir -p $(@D)
	$(ARM_CC) $(ARM_ARCH) -g $(REPRO) -c $< -o $@

# rustc drives the link as for the Phase 1 kernel, with tasks.ld and an arena
# of (capacity + 1) stack slots, the lowest one an unused moat. kstart.S
# (Phase 1) supplies the entry, the vectors and the semihosting exit. The
# "many" cases get their expected order checksum from the Python oracle; the
# job cases also get --cfg tmodel_jobs and RT_JOBS, the async cases
# --cfg tmodel_async, RT_JOBS, RT_SLOT and a pool of capacity x slot bytes
# (every other image an empty one), the overflow cases --cfg tgroup_overflow.
# Each case's parameters in a stamp file, rewritten only when they change, so
# that editing a TASKS_CFG_<case> rebuilds that image and nothing else (the
# stamp is checked on every run; its time changes only with its content).
.PHONY: tasks-cfg-check
tasks-cfg-check: ;
$(QEMU_OUT)/tasks-%.cfg: tasks-cfg-check
	@mkdir -p $(@D)
	@printf '%s\n' '$(TASKS_CFG_$*)' | cmp -s - $@ 2>/dev/null || printf '%s\n' '$(TASKS_CFG_$*)' > $@

$(QEMU_OUT)/tasks-%.elf: $(FIXTURE)/tasks.rs $(QEMU_OUT)/kstart.o $(QEMU_OUT)/switch.o $(QEMU_OUT)/tasks-%.cfg $(TASKS_LD) tests/qemu/tasks_oracle.py | need-rust need-arm
	@mkdir -p $(@D)
	@test -n "$(TASKS_CFG_$*)" || { echo "no TASKS_CFG_$* for $@"; exit 1; }
	set -- $(TASKS_CFG_$*); \
	jobs=$${5:-0}; slot=$${6:-0}; model=; \
	case "$$1" in jobs_*) model='--cfg tmodel_jobs';; async_*) model='--cfg tmodel_async';; overflow*) model='--cfg tgroup_overflow';; esac; \
	expect=0x0; case "$$1" in \
	  many) expect=$$($(PYTHON) -I tests/qemu/tasks_oracle.py $$2 $$4);; \
	  jobs_many|jobs_full|async_many|async_full) expect=$$($(PYTHON) -I tests/qemu/tasks_oracle.py $$jobs $$4);; \
	esac; \
	RT_TASKS=$$2 RT_STACK=$$3 RT_YIELDS=$$4 RT_JOBS=$$jobs RT_SLOT=$$slot RT_EXPECT=$$expect \
	$(RUSTC) $(RUST_FLAGS) $(RUST_LINK_BASE) -C link-arg=-Wl,-T,$(TASKS_LD) \
	    -C link-arg=-Wl,--defsym=__task_arena_size=$$(( ($$2 + 1) * $$3 )) \
	    -C link-arg=-Wl,--defsym=__async_pool_size=$$(( jobs * slot )) \
	    -C link-arg=$(QEMU_OUT)/kstart.o -C link-arg=$(QEMU_OUT)/switch.o \
	    --cfg tcase_$$1 $$model --emit link -o $@ $(FIXTURE)/tasks.rs

# ---- emulator-only exception reporting (a step toward ROADMAP 3a) ------------

# The reporting vectors and two fault triggers at known addresses (assembly;
# exc_vectors.S says why).
$(QEMU_OUT)/exc_vectors.o: $(FIXTURE)/exc_vectors.S | need-arm
	@mkdir -p $(@D)
	$(ARM_CC) $(ARM_ARCH) -g $(REPRO) -c $< -o $@

# rustc drives the link as for the Phase 1 kernel (link.ld, kstart.o); the
# case stem selects the fault: undef, dabt or pabt.
$(QEMU_OUT)/exc-%.elf: $(FIXTURE)/exc.rs $(QEMU_OUT)/kstart.o $(QEMU_OUT)/exc_vectors.o $(FIXTURE)/link.ld | need-rust need-arm
	@mkdir -p $(@D)
	$(RUSTC) $(RUST_FLAGS) $(RUST_LINK) -C link-arg=$(QEMU_OUT)/kstart.o -C link-arg=$(QEMU_OUT)/exc_vectors.o \
	    --cfg ecase_$* --emit link -o $@ $(FIXTURE)/exc.rs

# ---- Phase 2 GT-I9195 proof-of-execution payload (device image) -----------

# The device entry stub (ARM asm): halt-only vectors + zImage header, handoff
# capture, mask IRQ/FIQ, VBAR, stack, zero .bss, call Rust, then a masked wfi
# halt. NO svc in the image.
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

# The negative-test image: the same payload.bin, packed with the magic
# "INVALID!". The kernel slot stays the real payload on purpose (docs/phase-2,
# "Trial kit"). Not flashed by any target.
$(PAYLOAD_INVALID_IMG): $(PAYLOAD_BIN) tools/pack_bootimg.py
	$(PYTHON) -I tools/pack_bootimg.py --kernel $< --output $@ --invalid-magic

payload-invalid: $(PAYLOAD_INVALID_IMG) ## Build the Phase 2 NEGATIVE-TEST image (magic "INVALID!", built to be rejected; not the payload image)
	@echo 'NEGATIVE-TEST IMAGE, NOT THE PAYLOAD: payload-invalid.img has the magic "INVALID!" and is built to be rejected.'
	@echo "INVALID-MAGIC-NEGATIVE-TEST sha256 $$(sha256sum < $(PAYLOAD_INVALID_IMG) | cut -d' ' -f1)  payload-invalid.img  ($$(stat -c %s $(PAYLOAD_INVALID_IMG)) bytes)"

# ---- Phase 2 image 2: the text console (device image) -----------------------

# One stamp file per optimisation level; making one removes the others, so the
# image is rebuilt whenever CONSOLE_OPT differs from the level it was built at.
$(CONSOLE_OPT_STAMP):
	@mkdir -p $(@D)
	@rm -f $(CONSOLE_OUT)/opt-level-*.stamp
	@touch $@

# rustc drives the link exactly as for the first image: the same kstart.o, the
# same link.ld. main.rs is the crate root; the other files are its modules.
$(CONSOLE_ELF): $(CONSOLE_SRC) $(PAYLOAD_OUT)/kstart.o $(PAYLOAD_DIR)/link.ld $(CONSOLE_OPT_STAMP) | need-rust need-arm
	@mkdir -p $(@D)
	$(RUSTC) $(RUST_FLAGS) -C opt-level=$(CONSOLE_OPT) --crate-name revival_console \
	    $(RUST_PAYLOAD_LINK) -C link-arg=$(PAYLOAD_OUT)/kstart.o \
	    --emit link -o $@ $(CONSOLE_DIR)/main.rs

# The exact kernel-slot bytes the stock bootloader would run (flat binary).
$(CONSOLE_BIN): $(CONSOLE_ELF)
	$(ARM_OBJCOPY) -O binary $< $@

# The Android boot image v0 around them (not flashed by any target).
$(CONSOLE_IMG): $(CONSOLE_BIN) tools/pack_bootimg.py
	$(PYTHON) -I tools/pack_bootimg.py --kernel $< --output $@

# The modules that do not know the board (fb, console, font, atags), built for
# this machine with the standard test harness. No optimisation, so arithmetic
# overflow is checked while the tests run.
$(CONSOLE_HOST_TESTS): tests/boot/console_host.rs $(CONSOLE_SRC) | need-rust
	@mkdir -p $(@D)
	$(RUSTC) --edition 2021 --test -D warnings -C linker=$(HOST_CC) \
	    --remap-path-prefix $(CURDIR)=. -o $@ tests/boot/console_host.rs

console: $(CONSOLE_BIN) $(CONSOLE_IMG) ## Build the Phase 2 console image (.bin kernel slot + .img boot image)
	@cd $(CONSOLE_OUT) && sha256sum console.bin console.img

console-sizes: $(CONSOLE_ELF) ## Print the console image's size at opt-level 2, s and z, its largest functions and its wait loop (information, not a test)
	@for opt in 2 s z; do \
	  $(MAKE) --no-print-directory -s BUILD=$(OUT)/console-opt-$$opt CONSOLE_OPT=$$opt console >/dev/null; \
	  echo "console.bin at opt-level $$opt: $$(stat -c %s $(OUT)/console-opt-$$opt/boot-serrano-console/console.bin) bytes"; \
	done
	@echo "# largest symbols in $(notdir $(CONSOLE_ELF)) (opt-level $(CONSOLE_OPT)): address, size, kind, name"
	@$(ARM_NM) -S -C --size-sort $(CONSOLE_ELF) | tail -n 14
	@echo "# console_tick_wait: the instructions of one turn of the wait loop"
	@$(ARM_OBJDUMP) -d --no-show-raw-insn $(CONSOLE_ELF) | awk '/<console_tick_wait>:/{on=1} on&&NF==0{exit} on'

console-sample: ## Write the host oracle's sample console screen as a PNG picture (no build needed)
	@mkdir -p $(CONSOLE_OUT)
	@$(PYTHON) -m tests.boot.console_v2 --png $(CONSOLE_OUT)/console-sample.png

build: $(PROBE_ELFS) $(PROBE_BINS) $(ALLOC_ELF) $(KERNEL_ELFS) $(TASKS_ELFS) $(EXC_ELFS) $(PAYLOAD_BIN) $(PAYLOAD_IMG) $(CONSOLE_BIN) $(CONSOLE_IMG) ## Build every artifact that exists today (the ARMv7-A probe, allocator, Rust kernel, task-experiment, exception-report and the two Phase 2 images)
	@cd $(QEMU_OUT) && sha256sum probe-*.elf probe-*.bin alloc.elf kernel-*.elf $(notdir $(TASKS_ELFS)) $(notdir $(EXC_ELFS))
	@cd $(PAYLOAD_OUT) && sha256sum payload.elf payload.bin payload.img
	@cd $(CONSOLE_OUT) && sha256sum console.elf console.bin console.img

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

test: test-build test-unit test-qemu test-rust test-tasks test-exceptions test-payload test-console test-repro ## Run every automated test (build, unit, QEMU, Rust kernel, task experiment, exception reports, the two Phase 2 images, reproducibility)

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

test-tasks: $(TASKS_ELFS) | need-qemu need-arm ## Run the emulator-only task experiment (ADR 0003): 1,000 and 10,000 tasks, a full table, a stack overrun, a yield too deep for a switch, an overrun found at a task's exit, a fault that leaves the failed stack untouched, tasks that return, registers held across switches; 1,000 and 100,000 run-to-completion jobs, a full queue, a job that overruns the runner's stack; 1,000 and 100,000 stackless (async) tasks, a full pool, a task that overruns the executor's stack
	@mkdir -p $(LOGS)
	@tests/qemu/run.sh qemu-tasks-1000 $(QEMU_OUT)/tasks-many-1k.elf $(LOGS)/tasks-many-1k.log 0 \
	    "tasks: PASS many (1000 tasks x 100 yields)"
	@tests/qemu/run.sh qemu-tasks-10000 $(QEMU_OUT)/tasks-many-10k.elf $(LOGS)/tasks-many-10k.log 0 \
	    "tasks: PASS many (10000 tasks x 10 yields)"
	@tests/qemu/run.sh qemu-tasks-table-full $(QEMU_OUT)/tasks-full.elf $(LOGS)/tasks-full.log 0 \
	    "tasks: PASS full (spawn 65 of 64 refused; the 64 tasks then ran 192 iterations)"
	@tests/qemu/run.sh qemu-tasks-stack-overrun $(QEMU_OUT)/tasks-overflow.elf $(LOGS)/tasks-overflow.log 1 \
	    "tasks: FAULT found by the guard-word check at the task's next yield (task 1, 3 iterations before it); no task resumed"
	@tests/qemu/run.sh qemu-tasks-stack-pointer $(QEMU_OUT)/tasks-overflow-sp.elf $(LOGS)/tasks-overflow-sp.log 1 \
	    "tasks: FAULT found by the stack-pointer check at the task's yield (task 1, 3 iterations before it); no task resumed"
	@tests/qemu/run.sh qemu-tasks-overrun-at-exit $(QEMU_OUT)/tasks-overflow-exit.elf $(LOGS)/tasks-overflow-exit.log 1 \
	    "tasks: FAULT found by the guard-word check at the task's exit (task 1, 3 iterations before it); no task resumed"
	@tests/qemu/run.sh qemu-tasks-fault-leaves-stack $(QEMU_OUT)/tasks-overflow-moat.elf $(LOGS)/tasks-overflow-moat.log 1 \
	    "tasks: FAULT found by the stack-pointer check in the lowest slot; the failed stack was left untouched: guard word intact, moat unchanged"
	@tests/qemu/run.sh qemu-tasks-return $(QEMU_OUT)/tasks-return.elf $(LOGS)/tasks-return.log 0 \
	    "tasks: PASS return (wave 1: 64 tasks returned and 64 slots reclaimed; spawn from a running task refused; wave 2: 64 tasks in the same slots returned)"
	@tests/qemu/run.sh qemu-tasks-registers $(QEMU_OUT)/tasks-registers.elf $(LOGS)/tasks-registers.log 0 \
	    "tasks: PASS registers (64 tasks each held 8 values across 50 switches; none changed)"
	@tests/qemu/run.sh qemu-jobs-1000 $(QEMU_OUT)/tasks-jobs-1k.elf $(LOGS)/tasks-jobs-1k.log 0 \
	    "tasks: PASS jobs many (1000 jobs x 100 steps)"
	@tests/qemu/run.sh qemu-jobs-100000 $(QEMU_OUT)/tasks-jobs-100k.elf $(LOGS)/tasks-jobs-100k.log 0 \
	    "tasks: PASS jobs many (100000 jobs x 10 steps)"
	@tests/qemu/run.sh qemu-jobs-queue-full $(QEMU_OUT)/tasks-jobs-full.elf $(LOGS)/tasks-jobs-full.log 0 \
	    "tasks: PASS jobs full (job 65 of 64 refused; the 64 jobs then ran 192 steps in the expected order)"
	@tests/qemu/run.sh qemu-jobs-stack-overrun $(QEMU_OUT)/tasks-jobs-overflow.elf $(LOGS)/tasks-jobs-overflow.log 1 \
	    "tasks: FAULT found after the overrunning job's step, before the next job ran"
	@tests/qemu/run.sh qemu-async-1000 $(QEMU_OUT)/tasks-async-1k.elf $(LOGS)/tasks-async-1k.log 0 \
	    "tasks: PASS async many (1000 tasks x 100 awaits)"
	@tests/qemu/run.sh qemu-async-100000 $(QEMU_OUT)/tasks-async-100k.elf $(LOGS)/tasks-async-100k.log 0 \
	    "tasks: PASS async many (100000 tasks x 10 awaits)"
	@tests/qemu/run.sh qemu-async-pool-full $(QEMU_OUT)/tasks-async-full.elf $(LOGS)/tasks-async-full.log 0 \
	    "tasks: PASS async full (task 65 of 64 refused; a spawn from a running task refused; the 64 tasks then ran 192 steps in the expected order)"
	@tests/qemu/run.sh qemu-async-stack-overrun $(QEMU_OUT)/tasks-async-overflow.elf $(LOGS)/tasks-async-overflow.log 1 \
	    "tasks: FAULT found after the overrunning task's poll, before the next task was polled"
	@export LC_ALL=C; \
	  refs=$$($(ARM_NM) -u -A $(QEMU_OUT)/kstart.o $(QEMU_OUT)/switch.o | awk '{print $$NF}' | sort -u); \
	  defs=$$($(ARM_NM) --defined-only $(QEMU_OUT)/tasks-many-1k.elf | awk '{print $$NF}' | sort -u); \
	  missing=$$(comm -23 <(printf '%s\n' $$refs) <(printf '%s\n' $$defs) | tr '\n' ' '); \
	  u=$$($(ARM_NM) -u $(QEMU_OUT)/tasks-many-1k.elf | wc -l | tr -d ' '); \
	  if [ -z "$$missing" ] && [ "$$u" = 0 ]; then \
	    echo "PASS build-tasks-symbols (every symbol kstart.o and switch.o reference, weak ones included, is defined in the image; none is undefined)"; \
	  else echo "FAIL build-tasks-symbols: referenced but not defined in the image: $$missing; undefined: $$u"; exit 1; fi
	@n=$$($(ARM_OBJDUMP) -d $(QEMU_OUT)/tasks-many-1k.elf | grep -cE '\s(svc|swi|smc|hvc)\s' || true); \
	  if [ "$$n" = 1 ]; then echo "PASS build-tasks-one-svc (only the semihosting exit; the context switch makes no system call)"; \
	  else echo "FAIL build-tasks-one-svc: found $$n"; exit 1; fi

test-exceptions: $(EXC_ELFS) | need-qemu need-arm ## Run the emulator-only exception reports (a step toward ROADMAP 3a): an undefined instruction, a data abort and a prefetch abort, each reported with its kind and address, then a halt
	@mkdir -p $(LOGS)
	@QEMU_MEM=64M tests/qemu/run.sh qemu-exc-undefined-instruction $(QEMU_OUT)/exc-undef.elf $(LOGS)/exc-undef.log 1 \
	    "exception: as expected (undefined instruction at the expected pc); halted"
	@QEMU_MEM=64M tests/qemu/run.sh qemu-exc-data-abort $(QEMU_OUT)/exc-dabt.elf $(LOGS)/exc-dabt.log 1 \
	    "exception: as expected (data abort at the expected pc, fault address and status: synchronous external abort, a read); halted"
	@QEMU_MEM=64M tests/qemu/run.sh qemu-exc-prefetch-abort $(QEMU_OUT)/exc-pabt.elf $(LOGS)/exc-pabt.log 1 \
	    "exception: as expected (prefetch abort at the expected pc, fault address and status: synchronous external abort); halted"

test-payload: $(PAYLOAD_BIN) $(PAYLOAD_IMG) $(PAYLOAD_INVALID_IMG) $(PAYLOAD_OUT)/kstart.o tests/boot/run_payload.py tests/boot/read_bootimg.py tests/boot/check_negative_img.py tests/boot/serrano_v1.py tests/boot/payload_hosted_libc.rs $(FIXTURE)/hosted_std.rs tests/build/check_image_integrity.sh | need-qemu need-arm need-rust ## Boot the Phase 2 payload in QEMU (paint the framebuffers, inject MDP4 values and a fault), and check the handoff, the packer, the negative-test image, the frozen hashes and reproducibility
	@mkdir -p $(LOGS) $(PAYLOAD_OUT)/neg
	@echo "# (a) run the exact kernel-slot bytes; the framebuffers must match the host oracle, with the MDP4 value absent, injected, and faulting, a device-like handoff, and a relocated image"
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
	@$(MAKE) --no-print-directory -s BUILD=$(OUT)/payload-repro-a payload payload-invalid >/dev/null
	@$(MAKE) --no-print-directory -s BUILD=$(OUT)/payload-repro-b payload payload-invalid >/dev/null
	@if cmp -s $(OUT)/payload-repro-a/boot-serrano/payload.bin $(OUT)/payload-repro-b/boot-serrano/payload.bin \
	    && cmp -s $(OUT)/payload-repro-a/boot-serrano/payload.img $(OUT)/payload-repro-b/boot-serrano/payload.img; then \
	  echo "PASS payload-repro-identical (payload.bin and payload.img byte-identical across two clean builds)"; \
	else echo "FAIL payload-repro-identical"; exit 1; fi
	@if cmp -s $(OUT)/payload-repro-a/boot-serrano/payload-invalid.img $(OUT)/payload-repro-b/boot-serrano/payload-invalid.img; then \
	  echo "PASS payload-invalid-repro-identical (payload-invalid.img byte-identical across two clean builds)"; \
	else echo "FAIL payload-invalid-repro-identical"; exit 1; fi
	@echo "# (e) negative-test image: payload.img with the magic INVALID! and nothing else changed"
	@$(EXPECT) payload-invalid-magic-only 0 "OK" $(LOGS)/payload-invalid-check.log -- \
	    $(PYTHON) -m tests.boot.check_negative_img $(PAYLOAD_IMG) $(PAYLOAD_INVALID_IMG)
	@$(EXPECT) payload-invalid-rejected-by-reader nonzero "magic b'INVALID!' != b'ANDROID!'" \
	    $(LOGS)/payload-invalid-read.log -- $(PYTHON) -m tests.boot.read_bootimg $(PAYLOAD_INVALID_IMG)
	@echo "# (f) frozen payload: payload.bin and payload.img are the reviewed v1.3 bytes"
	@bin=$$(sha256sum < $(PAYLOAD_BIN) | cut -d' ' -f1); img=$$(sha256sum < $(PAYLOAD_IMG) | cut -d' ' -f1); \
	  if [ "$$bin" = "$(PAYLOAD_BIN_SHA256)" ] && [ "$$img" = "$(PAYLOAD_IMG_SHA256)" ]; then \
	    echo "PASS payload-frozen (payload.bin $$bin, payload.img $$img: the reviewed v1.3 bytes)"; \
	  else echo "FAIL payload-frozen: payload.bin $$bin (want $(PAYLOAD_BIN_SHA256)), payload.img $$img (want $(PAYLOAD_IMG_SHA256)); the payload is frozen, a change needs a new review"; exit 1; fi

test-console: $(CONSOLE_BIN) $(CONSOLE_IMG) $(CONSOLE_HOST_TESTS) tests/boot/run_console.py tests/boot/console_v2.py tests/boot/run_payload.py tests/boot/serrano_v1.py tests/boot/read_bootimg.py tools/gen_console_font.py $(CONSOLE_DIR)/font.txt tests/build/check_image_integrity.sh | need-qemu need-arm need-rust ## Boot the Phase 2 console image in QEMU (byte-exact screens for plain, device-like, malformed and random tag lists, alignment checking on, a moved image and a fault), run its modules' host tests, and check its size, its build attributes, that it has no panic code, the packer, reproducibility and the pinned hashes
	@mkdir -p $(LOGS) $(CONSOLE_OUT)/neg
	@echo "# (a) build checks on the console image"
	@$(EXPECT) console-font-generated 0 "OK font.rs matches font.txt" $(LOGS)/console-font.log -- \
	    $(PYTHON) -I tools/gen_console_font.py --check
	@size=$$(stat -c %s $(CONSOLE_BIN)); \
	  if [ "$$size" -le $(CONSOLE_MAX_BYTES) ]; then echo "PASS console-size (console.bin is $$size bytes at opt-level $(CONSOLE_OPT); limit $(CONSOLE_MAX_BYTES))"; \
	  else echo "FAIL console-size: console.bin is $$size bytes at opt-level $(CONSOLE_OPT); limit $(CONSOLE_MAX_BYTES)"; exit 1; fi
	@n=$$($(ARM_OBJDUMP) -d $(CONSOLE_ELF) | grep -cE '\s(svc|swi|smc|hvc)\s' || true); \
	  if [ "$$n" = 0 ]; then echo "PASS console-no-system-calls (zero svc/swi/smc/hvc)"; \
	  else echo "FAIL console-no-system-calls: found $$n"; exit 1; fi
	@u=$$($(ARM_NM) -u $(CONSOLE_ELF) | wc -l | tr -d ' '); \
	  if [ "$$u" = 0 ]; then echo "PASS console-symbols (no undefined symbols; Rust links its own core)"; \
	  else echo "FAIL console-symbols: $$u undefined"; $(ARM_NM) -u $(CONSOLE_ELF); exit 1; fi
	@a=$$($(ARM_READELF) -A $(CONSOLE_ELF)); \
	  grep -q 'Tag_CPU_arch: v7$$' <<<"$$a" && grep -q 'Tag_CPU_arch_profile: Application' <<<"$$a" \
	  && $(ARM_READELF) -h $(CONSOLE_ELF) | grep -q 'soft-float ABI' \
	  && echo "PASS console-elf-attributes (ARMv7-A, Application, soft-float EABI)" \
	  || { echo "FAIL console-elf-attributes"; exit 1; }
	@p=$$($(ARM_NM) $(CONSOLE_ELF) | grep -cE 'panicking|4core3fmt' || true); \
	  if [ "$$p" = 0 ]; then echo "PASS console-no-panic-code (no core::panicking and no core::fmt symbol in the linked image: nothing in it can panic)"; \
	  else echo "FAIL console-no-panic-code: $$p symbols"; $(ARM_NM) -C $(CONSOLE_ELF) | grep -E 'panicking|core::fmt'; exit 1; fi
	@tests/build/check_image_integrity.sh $(CONSOLE_BIN) $(CONSOLE_OUT)/neg console
	@echo "# (b) the board-independent modules, built for this machine, pass their host tests"
	@$(EXPECT) console-host-tests 0 "test result: ok" $(LOGS)/console-host.log -- $(CONSOLE_HOST_TESTS)
	@echo "# (c) run the exact kernel-slot bytes in QEMU; every screen must match the host oracle byte for byte"
	@syms=$$($(ARM_NM) -S $(CONSOLE_ELF)); \
	  halt=$$(awk '$$NF=="halt_loop"{print $$1}' <<<"$$syms"); \
	  wait=$$(awk 'NF==4 && $$4=="console_tick_wait"{print $$1}' <<<"$$syms"); \
	  size=$$(awk 'NF==4 && $$4=="console_tick_wait"{print $$2}' <<<"$$syms"); \
	  if [ -z "$$halt" ] || [ -z "$$wait" ] || [ -z "$$size" ]; then \
	    echo "FAIL qemu-console: halt_loop, or console_tick_wait with its size, is not in $(CONSOLE_ELF)"; exit 1; fi; \
	  $(PYTHON) -m tests.boot.run_console --image $(CONSOLE_BIN) --workdir $(CONSOLE_OUT)/qemu \
	      --halt-addr 0x$$halt --wait-addr 0x$$wait --wait-size 0x$$size
	@echo "# (d) packer: an independent reader validates every boot-image field"
	@$(EXPECT) console-bootimg-valid 0 "OK" $(LOGS)/console-read.log -- \
	    $(PYTHON) -m tests.boot.read_bootimg $(CONSOLE_IMG)
	@echo "# (e) reproducibility: two clean builds give byte-identical .bin and .img"
	@rm -rf $(OUT)/console-repro-a $(OUT)/console-repro-b
	@$(MAKE) --no-print-directory -s BUILD=$(OUT)/console-repro-a console >/dev/null
	@$(MAKE) --no-print-directory -s BUILD=$(OUT)/console-repro-b console >/dev/null
	@if cmp -s $(OUT)/console-repro-a/boot-serrano-console/console.bin $(OUT)/console-repro-b/boot-serrano-console/console.bin \
	    && cmp -s $(OUT)/console-repro-a/boot-serrano-console/console.img $(OUT)/console-repro-b/boot-serrano-console/console.img \
	    && cmp -s $(OUT)/console-repro-a/boot-serrano-console/console.bin $(CONSOLE_BIN); then \
	  echo "PASS console-repro-identical (console.bin and console.img byte-identical across two clean builds, and console.bin identical to this build's)"; \
	else echo "FAIL console-repro-identical"; exit 1; fi
	@echo "# (f) frozen image: console.bin and console.img are the reviewed bytes"
	@bin=$$(sha256sum < $(CONSOLE_BIN) | cut -d' ' -f1); img=$$(sha256sum < $(CONSOLE_IMG) | cut -d' ' -f1); \
	  if [ -z "$(CONSOLE_BIN_SHA256)" ] && [ -z "$(CONSOLE_IMG_SHA256)" ]; then \
	    echo "NOTE console-frozen: no hash is pinned yet, so this is not a test; console.bin $$bin, console.img $$img ($$(stat -c %s $(CONSOLE_IMG)) bytes)"; \
	  elif [ "$$bin" = "$(CONSOLE_BIN_SHA256)" ] && [ "$$img" = "$(CONSOLE_IMG_SHA256)" ]; then \
	    echo "PASS console-frozen (console.bin $$bin, console.img $$img: the reviewed bytes)"; \
	  else echo "FAIL console-frozen: console.bin $$bin (want $(CONSOLE_BIN_SHA256)), console.img $$img (want $(CONSOLE_IMG_SHA256)); the image is frozen, a change needs a new review"; exit 1; fi

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

# ---- measurements (not tests, not part of check) ---------------------------

measure-tasks: | need-qemu need-arm need-rust ## Measure the task experiment (ADR 0003): task counts up to QEMU's RAM, instructions per switch, bytes, job counts and instructions per job step, stackless task counts, instructions per step and bytes. Prints figures; slow; not part of check
	@MAKE='$(MAKE)' tests/qemu/measure_tasks.sh $(OUT)/measure

# ---- interactive (not tests) ----------------------------------------------

qemu-run: $(QEMU_OUT)/probe-0.elf | need-qemu ## Run the checksum probe in QEMU interactively (Ctrl-A X quits)
	$(QEMU) -M virt -cpu cortex-a15 -m 64M -nic none -nographic -semihosting-config enable=on,target=native -kernel $<

qemu-debug: $(QEMU_OUT)/probe-0.elf | need-qemu ## Start QEMU halted with a GDB server on port 1234
	@echo "In another terminal: gdb-multiarch $< -ex 'target remote :1234'"
	$(QEMU) -M virt -cpu cortex-a15 -m 64M -nic none -nographic -semihosting-config enable=on,target=native -s -S -kernel $<
