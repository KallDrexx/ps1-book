# Chapter 31 quiz

Answers are hidden under each question.

**1.** A flag byte is `0x5A`. Which items does it announce, in order, and how many input bytes follow it?

<details><summary>Answer</summary>
`0x5A` = `01011010b`, read from the least significant bit: bit0 = 0 reference, bit1 = 1 literal, bit2 = 0 reference, bit3 = 1 literal, bit4 = 1 literal, bit5 = 0 reference, bit6 = 1 literal, bit7 = 0 reference. That is 4 references (2 bytes each) and 4 literals (1 byte each): 12 input bytes follow the flag. They produce between 4 + 4 x 3 = 16 and 4 + 4 x 18 = 76 output bytes.
</details>

**2.** A reference's two bytes are `3A 52`. What ring position and length do they name?

<details><summary>Answer</summary>
`pos = 0x3A | ((0x52 & 0xF0) << 4) = 0x3A | 0x500 = 0x53A` (1338); `len = (0x52 & 0x0F) + 3 = 2 + 3 = 5`. The decoder copies 5 bytes starting at `ring[0x53A]`.
</details>

**3.** The cursor starts at 4078. After the decoder has produced 20 bytes, where is it?

<details><summary>Answer</summary>
`(4078 + 20) & 4095 = 4098 & 4095 = 2`: it wrapped past slot 4095 after 18 bytes. Every output byte, literal or copied, advances it by one.
</details>

**4.** Encode `AAAAAAAAAA` (ten `A`s). Give the stream in hex.

<details><summary>Answer</summary>
The first `A` is a literal at ring slot 4078 (`0xFEE`). The other nine are one reference to slot 4078 with length 9: it reads the byte it has just written, and each copied byte makes the next one available. `b0 = 0xEE`, `b1 = (0xFEE >> 4 & 0xF0) | (9 - 3) = 0xF0 | 6 = 0xF6`. The flag byte has bit0 = 1 (literal), bit1 = 0 (reference): `0x01`. Stream: `01 41 EE F6` (4 bytes for 10).
</details>

**5.** Why does the reference store an *absolute ring position* rather than a distance back from the cursor?

<details><summary>Answer</summary>
The decoder then copies from `ring[pos]` directly, with no subtraction; the compressor does the arithmetic once, `(4078 + i - d) & 4095` for a match found `d` bytes back at data index `i`. (The ring holds only the last 4096 bytes, so no match can reach further back; Appendix E.5's packers stay within 4095.) Storing the distance by mistake is the most common bug: the output looks nearly right but is wrong.
</details>

**6.** Which bytes does the `.TPK` header's CRC-32 cover, and why?

<details><summary>Answer</summary>
The **uncompressed** blob (the concatenated TIMs). The decoder's job is to rebuild those bytes; checking them catches a damaged disc read and any decoder bug in one step, whatever the compressor did. A checksum of the compressed stream would pass for a decoder that rebuilds the wrong data.
</details>

**7.** A 16,896-byte pack compresses to a 5,388-byte file. At 300 KB/s, how much disc time does that save, and how does it compare with a decode of 557,000 cycles at 33.8688 MHz?

<details><summary>Answer</summary>
Saved bytes: 16,896 - 5,388 = 11,508. At 300,000 bytes/s that is about 38 ms (77 ms at single speed). Decoding: 557,000 / 33,868,800 = 16.4 ms. So the pack loads about 22 ms faster even before counting seek time, and the saving grows with the compressibility of the data.
</details>

**8.** `lzss_decode` finds a reference of length 18 when only 10 output bytes remain. What must it do, and why not just copy 10?

<details><summary>Answer</summary>
Return an error (`TPK_ERR_DATA`) without writing past `dst_size`. The format says a reference that would overrun `out_size` is an error: a valid stream never does it, so it means the data is damaged. Clipping would hide the corruption (the CRC would catch it later at best); copying all 18 would write outside the buffer and corrupt the heap.
</details>

**9.** `tpkpack.py` is given the files `9.tim`, `10.tim`, `a.tim` and `B.TIM`. In which order do they become texture ids 0..3? How do you make the order obvious?

<details><summary>Answer</summary>
Plain string order compares characters: `10.tim` (`'1'` = 49), `9.tim` (`'9'` = 57), `B.TIM` (`'B'` = 66), `a.tim` (`'a'` = 97). So ids 0..3 are `10.tim`, `9.tim`, `B.TIM`, `a.tim`. Zero-pad numbered names (`00.tim`, `01.tim`, ..., `10.tim`) and use one case, and the order matches what you read.
</details>
