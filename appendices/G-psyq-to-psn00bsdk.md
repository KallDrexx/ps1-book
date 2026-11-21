# Appendix G: PsyQ to PSn00bSDK Name Map

For following older tutorials and the reference course (Sony's PsyQ `libgpu`/`libgte`/`libetc`/`libcd`/`libspu`/`libapi`
names) while writing PSn00bSDK 0.24 code. PSn00bSDK deliberately mirrors many PsyQ names, so a lot ports unchanged;
this appendix records where it does not.

**How it was checked.** Every "present" and "absent" below was decided by `grep -w` over the SDK headers in
`.toolchain/opt/psn00bsdk/include/libpsn00b/` (`inline_c.h`, `psxgte.h`, `psxgpu.h`, `psxspu.h`, `psxcd.h`, `psxapi.h`,
`psxetc.h`, `psxpad.h`, `stdlib.h`) and, for the GTE and GPU libraries, by listing the exported symbols of
`lib/libpsn00b/release/libpsxgte_exe_gprel.a` and `libpsxgpu_exe_gprel.a` with `nm`. "Absent" means: no declaration
in any header and no symbol in those libraries. Where a PsyQ function's exact signature or return value is from
memory rather than a document in this repository, the row says *PsyQ detail from memory*. The `gte_*` sequences are
built from the macro semantics in Appendix D; the ones marked *composed* are this book's constructions, not an SDK
function, and have not each been run through a verifier (the Chapter 25 to 27 sequences have).

Related: [Appendix D](D-gte-reference.md) (macros and registers), [Appendix F](F-troubleshooting.md) (the clobber defect).

## G.1 GTE: names that do not exist in 0.24

PSn00bSDK 0.24's `libpsxgte` exports only: `InitGeom`, `RotMatrix`, `HiRotMatrix`, `TransMatrix`, `ScaleMatrix`,
`ScaleMatrixL`, `MulMatrix`, `MulMatrix0`, `CompMatrixLV`, `ApplyMatrixLV`, `PushMatrix`, `PopMatrix`, `VectorNormalS`,
`Square0`, `SquareRoot0`, `SquareRoot12`, `isin`, `icos`, `hisin`, `hicos`. The per-vertex wrappers of the Sony library
are not there. Include `<inline_c.h>` after `<psxgte.h>` and use macro sequences.

| PsyQ function | Status in 0.24 | Replacement |
|---|---|---|
| `SetGeomOffset(x, y)` | absent | `gte_SetGeomOffset(x, y)` (whole pixels; the macro shifts them into 16.16) |
| `SetGeomScreen(h)` | absent | `gte_SetGeomScreen(h)` |
| `SetRotMatrix(&m)` | absent | `gte_SetRotMatrix(&m)` **(clobber defect, G.2)** |
| `SetTransMatrix(&m)` | absent | `gte_SetTransMatrix(&m)` **(clobber defect)** |
| `SetLightMatrix`, `SetColorMatrix` | absent | `gte_SetLightMatrix`, `gte_SetColorMatrix` **(clobber defect)** |
| `SetBackColor(r, g, b)`, `SetFarColor(r, g, b)` | absent | `gte_SetBackColor`, `gte_SetFarColor` (these declare their registers correctly) |
| `RotTransPers(v, &sxy, &p, &flag)` | absent | `gte_ldv0(v); gte_rtps(); gte_stsxy(&sxy); gte_stsz(&sz); gte_stflg(&flag);` Add `gte_stdp(&p)` for the depth-cue value (`IR0`, what PsyQ's `p` is) and `gte_stszotz(&otz)` for `SZ3 >> 2`, which is what PsyQ returned (Chapter 25). `gte_ldv0` takes a pointer |
| `RotTransPers3(v0, v1, v2, &sxy0, &sxy1, &sxy2, &p, &flag)` | absent | `gte_ldv3(v0, v1, v2); gte_rtpt(); gte_stsxy3(&sxy0, &sxy1, &sxy2); gte_stdp(&p); gte_stflg(&flag);` (`gte_ldv3c`/`gte_stsxy3c` for consecutive data, Chapter 27). Depth: `gte_stsz3(&z0, &z1, &z2)` |
| `RotTransPers4(v0..v3, ...)` | absent | *composed*: `gte_ldv3(v0, v1, v2); gte_rtpt(); gte_stsxy3(&s0, &s1, &s2);` **then** `gte_ldv0(v3); gte_rtps(); gte_stsxy(&s3);`. Store the first three before the `RTPS`, because it shifts the FIFO. Afterwards `SZ0..SZ3` = `v0..v3`. `FLAG` is cleared by each command: read it after each and OR |
| `RotAverage3(v0, v1, v2, &s0, &s1, &s2, &p, &otz, &flag)` | absent | *composed*: `gte_ldv3(...); gte_rtpt(); gte_stsxy3(...); gte_stdp(&p); gte_stflg(&flag); gte_avsz3(); gte_stotz(&otz);` |
| `RotAverage4(...)` | absent | *composed*: the `RotTransPers4` sequence, then `gte_avsz4(); gte_stotz(&otz);` |
| `RotNclip3(...)` | absent | *composed*: `gte_ldv3(...); gte_rtpt(); gte_nclip(); gte_stopz(&opz);` then the stores as above (PsyQ detail from memory: it also returned the `NCLIP` value) |
| `RotNclip4(...)` | absent | *composed*: as `RotNclip3`, then the fourth vertex as in `RotTransPers4` |
| `RotAverageNclip3(...)` | absent | *composed*: `gte_ldv3(...); gte_rtpt(); gte_stsxy3(...); gte_nclip(); gte_stopz(&opz); gte_avsz3(); gte_stotz(&otz); gte_stflg(&flag);` **Read `MAC0` (`stopz`) before `AVSZ3`: both write `MAC0`** |
| `RotAverageNclip4(...)` | absent | *composed*: `gte_ldv3(v0, v1, v2); gte_rtpt(); gte_stsxy3(&s0, &s1, &s2); gte_nclip(); gte_stopz(&opz); gte_ldv0(v3); gte_rtps(); gte_stsxy(&s3); gte_avsz4(); gte_stotz(&otz); gte_stflg(&flag);`. `NCLIP` must run on `v0, v1, v2` **before** the `RTPS` pushes the FIFO; after the `RTPS`, `SXY0..2` are `v1, v2, v3` |
| `NormalClip(sxy0, sxy1, sxy2)` | absent | `gte_ldsxy3(sxy0, sxy1, sxy2); gte_nclip(); gte_stopz(&area);` **values**, not pointers. Positive = clockwise on screen = front-facing here |
| `AverageZ3(sz0, sz1, sz2)` | absent | `gte_ldsz3(sz0, sz1, sz2); gte_avsz3(); gte_stotz(&otz);` |
| `AverageZ4(sz0, sz1, sz2, sz3)` | absent | `gte_ldsz4(sz0, sz1, sz2, sz3); gte_avsz4(); gte_stotz(&otz);` |

Chapter 25's project uses the setters, the `RotTransPers` and `NormalClip` sequences and `gte_ldsz4`/`gte_avsz4`;
Chapter 27 uses the batched forms.

**Other PsyQ `libgte` names checked and absent** (no header, no symbol): `ApplyRotMatrix`, `ApplyTransposeMatrixLV`,
`TransposeMatrix`, `MulRotMatrix`, `MulMatrix2`, `SetMulMatrix`, `SetMulRotMatrix`, `RotMatrixX/Y/Z`, `RotMatrixYXZ`,
`RotMatrixZYX`, `VectorNormal`, `Square12`, `ratan2`, `OuterProduct0/12`, `Lighting*`, `LocalLight`, `NormalColor*`,
`ColorDpq`, `ColorCol`, `DpqColor*`, `SetFogNear`, `SetFogFar`, `ReadRotMatrix` (the macro is `gte_ReadRotMatrix`),
`ReadGeomOffset` (macro `gte_ReadGeomOffset`). Use the commands of Appendix D (`gte_ll*`, `gte_nc*`, `gte_op*`, ...) or
write the arithmetic yourself.

**Names that keep their PsyQ spelling** (declared in `psxgte.h`, exported by `libpsxgte`): `InitGeom`, `RotMatrix`,
`TransMatrix`, `ScaleMatrix`, `ScaleMatrixL`, `MulMatrix`, `MulMatrix0`, `CompMatrixLV`, `ApplyMatrixLV`, `PushMatrix`,
`PopMatrix`, `VectorNormalS`, `Square0`, `SquareRoot0`, `SquareRoot12`, `isin`, `icos`, and the macros `rsin`, `rcos`,
`csin`, `ccos`. `HiRotMatrix`, `hisin`, `hicos` are PSn00bSDK additions.
Caveats from the chapters: `PushMatrix`/`PopMatrix` have one slot, and `RotMatrix` pushes and pops it itself
(Chapter 26); `MulMatrix` and `CompMatrixLV` replace the GTE's current matrix; `RotMatrix` and `isin`/`icos` angles are 4096 per
turn (the `psxgte.h` comments saying 131072 are wrong, Appendix D.6); `VectorNormalS` traps on large vectors (Appendix F.8).

## G.2 The clobber defect, in one place

`gte_SetRotMatrix`, `gte_SetTransMatrix`, `gte_SetLightMatrix` and `gte_SetColorMatrix` write `$t0` and `$t1` but declare
only `$t2` clobbered. Call them only from a `noipa` function (the book's `load_matrix()`); `noinline` is not enough
because `-fipa-ra` lets the caller keep values in `$t0`/`$t1` across the call. Full account: Appendix F.7. Where PsyQ
code says `SetRotMatrix(&m); SetTransMatrix(&m);`, write `load_matrix(&m);`.

## G.3 `inline_c.h` and Nugget's `inline_n.h`

`inline_c.h`'s own header says it is "basically identical to Nugget's `inline_n.h`". PsyQ's own inline GTE headers (from memory) used `gte_*` names too, so most PsyQ-style macro code compiles. Differences worth knowing:

* Plain command macros are `nop; nop; cop2 <word>`. A bare variant `gte_*_b()` (67 of them: `gte_rtps_b`, `gte_rtpt_b`,
  `gte_nclip_b`, `gte_avsz3_b`, `gte_avsz4_b`, `gte_mvmva_b`, the `rt*`/`ll*`/`lc*`, `nc*`, `dp*`, `op*`, `gp*`, `sqr*`
  families, ...) is **only** the `cop2` word, e.g. `gte_rtpt_b()` is `cop2 0x0280030`. With `_b` you place the two
  instructions between the last register write and the command yourself (Chapter 27, Appendix D.6).
* `gte_ld*` loads do not declare `"memory"`; put a compiler barrier before them if you just wrote the data.
* `gte_stflg` reads `FLAG` with `cfc2` and a `nop`.
* The `gte_nop` macro is commented out in the header.
* The names `gte_ldv0`, `gte_rtps`, `gte_stsxy`, ... are exactly the PsyQ ones; the setters above are the exception
  because of the defect.

## G.4 GPU (`libgpu`)

| PsyQ | PSn00bSDK 0.24 | Note |
|---|---|---|
| `ResetGraph(mode)`, `SetDispMask`, `VSync`, `VSyncCallback`, `DrawSync`, `DrawSyncCallback` | same | |
| `PutDispEnv`, `PutDrawEnv`, `SetDefDispEnv`, `SetDefDrawEnv` | same | `DISPENV`/`DRAWENV` fields differ (`DRAWENV` has `clip`, `ofs[2]`, `tw`, `tpage`, `dtd`, `dfe`, `isbg`...). 0.24 also has `PutDrawEnvFast`, `PutDispEnvRaw` |
| `GetDispEnv`, `GetDrawEnv` | absent | keep your own copy |
| `ClearOTag`, `ClearOTagR`, `DrawOTag`, `DrawOTagEnv`, `DrawPrim`, `AddPrim` | same | 0.24 adds `DrawOTagIRQ`, `DrawBuffer`, `EnqueueDrawOp`; `ClearOTagR(ot, length)` |
| `addPrim`, `addPrims`, `catPrim`, `termPrim`, `nextPrim`, `isendprim`, `setlen`, `setaddr`, `setcode` | same (macros) | |
| `setPolyF3/FT3/G3/GT3/F4/FT4/G4/GT4`, `setSprt`, `setSprt8/16`, `setTile`, `setTile1/8/16`, `setLineF2/G2/F3/G3/F4/G4`, `setFill`, `setSemiTrans`, `setShadeTex` | same | `setRGB0..3`, `setXY0/2/3/4`, `setXYWH`, `setUV0/3/4`, `setUVWH`, `setWH`, `setRECT`, `setVector`, `setTPage`, `setClut`, `setColor0..3` also present |
| `GetTPage(...)`, `GetClut(...)` | absent as functions | macros `getTPage(tp, abr, x, y)`, `getClut(x, y)` (lower-case `g`) |
| `LoadTPage`, `LoadClut` | absent | `LoadImage` of the TIM's rectangles, then compute the words (Chapters 30, 35). `GetTimInfo` (0.24, fills a `TIM_IMAGE`) and `GsGetTimInfo` exist |
| `LoadImage`, `StoreImage`, `MoveImage` | same | `LoadImage2`/`StoreImage2`/`MoveImage2` are non-blocking variants. `LoadImage` is asynchronous: `DrawSync(0)` before freeing the data |
| `ClearImage`, `FillImage` | absent | a `FILL` primitive (`setFill` + `DrawPrim`), or `DRAWENV.isbg` |
| `FntLoad`, `FntOpen`, `FntPrint`, `FntFlush`, `FntSort` | same | `FntSort(ot, pri, x, y, text)` draws through the ordering table (Chapter 38); from memory, PsyQ has no `FntSort` |
| `GetVideoMode`, `SetVideoMode` | present (0.24: `MODE_NTSC` / `MODE_PAL`) | |
| `GetODE`, `IsIdleGPU` | `GetODE` same; `IsIdleGPU` new | |
| `SetDrawMode`, `SetDrawArea`, `SetDrawOffset` (functions) | absent | the packet macros `setDrawTPage`, `setDrawArea`, `setDrawOffset`, `setTexWindow`, `setDrawStp` build the corresponding primitives |
| `GsInit`, `GsInitGraph` (`libgs` scene API) | absent | the book builds its own engine (`psxe`, Chapter 21). Only `GsGetTimInfo` and the `GsIMAGE` type of `libgs` exist |

## G.5 CD-ROM, API, events, pads, memory cards

| PsyQ | PSn00bSDK 0.24 | Note |
|---|---|---|
| `CdInit`, `CdControl`, `CdControlB`, `CdControlF`, `CdSync`, `CdIntToPos`, `CdPosToInt`, `CdGetSector`, `CdRead`, `CdReadSync`, `CdReadCallback`, `CdSyncCallback`, `CdReadyCallback`, `CdMix`, `CdSearchFile`, `CdLoadSession`, `CdStatus`, `CdMode`, `CdLastCom`, `CdLastPos` | same | `CdSearchFile` is stricter in 0.24 (upper case, leading backslash, Chapter 29). `CdMix(const CdlATV *)` |
| `CdReady`, `CdFlush`, `CdGetSession`, `CdSetDebug`, `CdReadFile`, `CdInitSnd`, `Ds*` (`libds`), `St*` (movie streaming) | absent | |
| | `CdReadRetry`, `CdReadBreak`, `CdCommand`, `CdAutoPauseCallback`, `CdGetToc`, `CdOpenDir`/`CdReadDir`, `CdGetVolumeLabel`, `CdIsoError`, `CdGetRegion`, `CdUnlock` | 0.24 additions |
| `InitHeap(addr, size)`, `malloc`, `free` | `InitHeap` in `<stdlib.h>`, same | |
| `EnterCriticalSection`, `ExitCriticalSection`, `OpenEvent`, `CloseEvent`, `EnableEvent`, `TestEvent`, `WaitEvent`, `DeliverEvent`, `FlushCache` | same (BIOS wrappers in `psxapi.h`) | |
| `PadInit`, `PadRead`, `PadStop` (libetc) | absent | the BIOS driver: `InitPAD(buf1, len1, buf2, len2)`, `StartPAD`, `StopPAD` (Chapter 22). `psxpad.h` defines the response/request structures |
| `InitCARD`, `StartCARD`, `StopCARD`, `_card_*`, `_bu_init` | same (BIOS wrappers) | `MemCardInit` and the memory-card libraries are absent |
| `VSync`, `ResetCallback`, `InterruptCallback`, `DMACallback`, `StopCallback`, `RestartCallback`, `SetDMAPriority` | same names (`psxetc.h`) | |

## G.6 SPU (`libspu`)

PSn00bSDK's SPU library is small. Most of PsyQ's `Spu*` API (`SpuSetVoiceAttr`, `SpuSetCommonAttr`, `SpuMalloc`,
`SpuInitMalloc`, `SpuSetReverb`, `SpuQuit`, `SpuSetKeyOnWithAttr`, `SpuGetVoiceVolume`) is **absent**; the SDK offers
the hardware registers directly and a few macros "for compatibility".

| PsyQ | PSn00bSDK 0.24 |
|---|---|
| `SpuInit()` | same (function) |
| `SpuWrite`, `SpuRead`, `SpuSetTransferMode`, `SpuSetTransferStartAddr`, `SpuIsTransferCompleted` | same (functions); also `SpuWritePartly`, `SpuGetTransferMode`, `SpuGetTransferStartAddr` |
| `SpuSetKey(on_off, voice_bits)` | same, as a macro writing `SPU_KEY_ON1/2` or `SPU_KEY_OFF1/2` |
| `SpuSetVoiceVolume(ch, l, r)`, `SpuSetVoicePitch`, `SpuSetVoiceStartAddr`, `SpuSetVoiceADSR(ch, ar, dr, sr, rr, sl)` | macros writing `SPU_CH_VOL_L/R`, `SPU_CH_FREQ`, `SPU_CH_ADDR`, `SPU_CH_ADSR1/2`. Addresses are in bytes in the macro (`getSPUAddr` divides by 8) |
| `SpuSetCommonMasterVolume`, `SpuSetCommonCDVolume`, `SpuSetCommonCDReverb`, `SpuSetCommonExtVolume`, `SpuSetReverbAddr`, `SpuSetIRQAddr` | macros |
| (none) | `getSPUAddr`, `getSPUSampleRate(rate)` (`rate * 4096 / 44100`), `getSPUADSR(...)` |
| `SpuSetVoiceAttr`, `SpuMalloc` | absent: the book keeps its own `audio_cfg` and allocator (Chapter 39) |

## G.7 Reading an old tutorial

1. Search the tutorial's calls in G.1, G.4 to G.6. A name in "same" rows needs no change.
2. Replace the GTE wrappers with the macro sequences; mind that macros take pointers or values per Appendix D.6.
3. Replace `SetRotMatrix`/`SetTransMatrix` with `load_matrix` (G.2).
4. Expect Y-up and different winding in older material: this book is Y-down, and `NCLIP > 0` is front-facing.
5. Check units: translations are vertex units; matrices are 4.12; `gte_SetGeomOffset` takes pixels.
