# Dogpile Report: bounded software security scanning evidence contracts

## Degraded Sources
Dogpile returned all successful source results. These sources failed or degraded:
- **stage1:codex_knowledge**: scillm HTTP 401: {"error":{"message":"Invalid API key","type":"authentication_error","code":401,"advice":"Auth failed. Use 'Authorization: Bearer sk-dev-proxy-123' header. Check that the scillm proxy is running on :4001.","skill":"/best-practices-scillm"}}
- **stage1:perplexity**: Skipped: Perplexity is retired for Dogpile; API calls are disabled. -> Use Dogpile's concurrent Brave question lane for free web-backed research.
- **stage1:readarr**: Skipped: Readarr/Usenet is disabled by default. -> Pass --with-readarr when local Readarr/ingest-book search is intentionally required.
- **stage1:wayback**: Skipped: Wayback archive lookup is disabled by default. -> Pass --with-wayback when historical snapshots are intentionally required.
- **stage1:feeds**: Skipped: Feed monitors are disabled by default. -> Pass --with-feeds to run configured consume-feed RSS monitors as a dry-run lane.
- **stage2:synthesis**: Error: scillm HTTP 401: {"error":{"message":"Invalid API key","type":"authentication_error","code":401,"advice":"Auth failed. Use 'Authorization: Bearer sk-dev-proxy-123' header. Check that the scillm proxy is running on :4001.","skill":"/best-practices-scillm"}}

> **Wayback Machine**: Skipped: Wayback archive lookup is disabled by default.
> Hint: Pass --with-wayback when historical snapshots are intentionally required.

## Codex Technical Overview
> Error: Error: scillm HTTP 401: {"error":{"message":"Invalid API key","type":"authentication_error","code":401,"advice":"Auth failed. Use 'Authorization: Bearer sk-dev-proxy-123' header. Check that the scillm proxy is running on :4001.","skill":"/best-practices-scillm"}}

## AI Research (Perplexity)
> Skipped: Perplexity is retired for Dogpile; API calls are disabled.
> Replacement: brave_questions
> Hint: Use Dogpile's concurrent Brave question lane for free web-backed research.

## Books & Usenet (Readarr)
> Skipped: Readarr/Usenet is disabled by default.
> Hint: Pass --with-readarr when local Readarr/ingest-book search is intentionally required.

## Feed Monitors
> Skipped: Feed monitors are disabled by default.
> Hint: Pass --with-feeds to run configured consume-feed RSS monitors as a dry-run lane.

## GitHub
### Repositories
No repositories found.

### Issues/Discussions
- **grahama1970/agent-skills**: [P1: Emit dogpile.security_research_packet.v1 with source-bearing provenance](None) (open)

## Web Results (Brave)
- **[GitHub - RUB-SysSec/EthBMC: The code repository for the 2020 Usenix Security paper "EthBMC: A Bounded Model Checker for Smart Contracts"](https://github.com/RUB-SysSec/EthBMC)**
  Note when analyzing big contracts you might have to increase Rusts stack size, see here. EthBMC 1.0.0 EthBMC: A Bounded Model Checker for Smart Contracts USAGE: ethbmc [FLAGS] [OPTIONS] &lt;INPUT&gt; FLAGS: -x, --acc The input is an Ethereum account address, must be used with parity backend, mainnet only --concrete-copy Use concrete calldatacopy -d, --debug-grap Dump debug graph after analysis --no-optimizations Disable all optimizations --dump-solver Dump all solver queries to ./queries -h, --help Prints help information --json Output json without logging --list The input is a list of Ethereum account address, writes the result to a csv file in the output folder --no-verify Skip verification phase.
- **[ETHBMC: A Bounded Model Checker for Smart Contracts | USENIX](https://www.usenix.org/conference/usenixsecurity20/presentation/frank)**
  Based on these insights, we present the design and implementation of, a bounded model checker based on symbolic execution which provides a precise model of the Ethereum network. We demonstrate its capabilities in a series of experiments. First, we compare against the eight aforementioned tools, showing that even relatively simple toy examples can obstruct other analyzers. Further proving that precise modeling is indispensable, we leverage ETHBmc capabilities for automatic vulnerability scanning.
- **[A Bounded Game Semantics Checker for Precise Smart Contract Analysis](https://arxiv.org/html/2512.22417)**
  Our method is based on game semantics, modelling computation as an interaction between a contract and its environment, reducing reasoning about unknown or malicious external contracts to trace enumeration. We implement this in a tool we refer to as YulToolkit, a bounded game-semantics checker for Yul, the intermediate language of Solidity.
- **[ETHBMC | Proceedings of the 29th USENIX Conference on Security Symposium](https://dl.acm.org/doi/10.5555/3489212.3489367)**
  For example, we discovered that a precise memory model is missing and inter-contract analysis is only partially supported. Based on these insights, we present the design and implementation of ETHBMC, a bounded model checker based on symbolic execution which provides a precise model of the Ethereum network.
- **[(PDF) Bounded and Shielded: Assessing Security Aspects and Trustworthiness of Smart Contracts](https://www.academia.edu/53584465/Bounded_and_Shielded_Assessing_Security_Aspects_and_Trustworthiness_of_Smart_Contracts)**
  This is <strong>an in-progress research project that aims to explore how archival science and cybersecurity can be applied to evaluate the trustworthiness and security of smart contracts</strong>.

## Concurrent Brave Questions
_Replacement for: perplexity_
### bounded software security scanning evidence contracts
- **[GitHub - RUB-SysSec/EthBMC: The code repository for the 2020 Usenix Security paper "EthBMC: A Bounded Model Checker for Smart Contracts"](https://github.com/RUB-SysSec/EthBMC)**
  Note when analyzing big contracts you might have to increase Rusts stack size, see here. EthBMC 1.0.0 EthBMC: A Bounded Model Checker for Smart Contracts USAGE: ethbmc [FLAGS] [OPTIONS] &lt;INPUT&gt; FLAGS: -x, --acc The input is an Ethereum account address, must be used with parity backend, mainnet only --concrete-copy Use concrete calldatacopy -d, --debug-grap Dump debug graph after analysis --no-optimizations Disable all optimizations --dump-solver Dump all solver queries to ./queries -h, --help Prints help information --json Output json without logging --list The input is a list of Ethereum account address, writes the result to a csv file in the output folder --no-verify Skip verification phase.
- **[ETHBMC: A Bounded Model Checker for Smart Contracts | USENIX](https://www.usenix.org/conference/usenixsecurity20/presentation/frank)**
  Based on these insights, we present the design and implementation of, a bounded model checker based on symbolic execution which provides a precise model of the Ethereum network. We demonstrate its capabilities in a series of experiments. First, we compare against the eight aforementioned tools, showing that even relatively simple toy examples can obstruct other analyzers. Further proving that precise modeling is indispensable, we leverage ETHBmc capabilities for automatic vulnerability scanning.
- **[A Bounded Game Semantics Checker for Precise Smart Contract Analysis](https://arxiv.org/html/2512.22417)**
  Our method is based on game semantics, modelling computation as an interaction between a contract and its environment, reducing reasoning about unknown or malicious external contracts to trace enumeration. We implement this in a tool we refer to as YulToolkit, a bounded game-semantics checker for Yul, the intermediate language of Solidity.

### bounded software security scanning evidence contracts sources evidence
- **[(PDF) Bounded and Shielded: Assessing Security Aspects and Trustworthiness of Smart Contracts](https://www.academia.edu/53584465/Bounded_and_Shielded_Assessing_Security_Aspects_and_Trustworthiness_of_Smart_Contracts)**
  The analysis will be made using the requirements of trustworthy records and the investigation of vulnerabilities related to the development and implementation of smart contracts. The expected contribution is to improve smart contracts’ trustworthiness as archival records and evidence.
- **[GitHub - RUB-SysSec/EthBMC: The code repository for the 2020 Usenix Security paper "EthBMC: A Bounded Model Checker for Smart Contracts"](https://github.com/RUB-SysSec/EthBMC)**
  The code repository for the 2020 Usenix Security paper &quot;EthBMC: A Bounded Model Checker for Smart Contracts&quot; - RUB-SysSec/EthBMC
- **[ETHBMC | Proceedings of the 29th USENIX Conference on Security Symposium](https://dl.acm.org/doi/10.5555/3489212.3489367)**
  Further proving that precise modeling is indispensable, we leverage ETHBMC capabilities for automatic vulnerability scanning. We perform a large-scale analysis of roughly 2.2 million accounts currently active on the blockchain and automatically generate 5,905 valid inputs which trigger a vulnerability. From these, 1,989 can destroy a contract at will (so called suicidal contracts) and the rest can be used by an adversary to arbitrarily extract money.

## Academic Papers (ArXiv)

## Videos (YouTube)
### Video Insights (Transcripts)
#### [Smart Contract Vulnerability Detection w/ Python Part 1](https://www.youtube.com/watch?v=AgkKC5tByhk)
> [Music] [Music] [Music] [Music] [Music] [Music] [Music] [Music] [Music] hello everyone welcome to Global hack week um in this session we're going to be talking about smart contract vulnerability detection um so if you are coming from the last stream where you learned how how to create smart contracts that's a kind of a great transition of like how to look out for the security of your smart contracts um you will be learning along with me throughout this stream um I've compiled a few different uh python libraries a few a few different tools to find the um vulnerabilities and kind of enhance the security of your smart contracts um I have like kind of like found a few different tools we can use um kind of in combination to find all those vulnerability uh but as web 3 is like a relatively like ...

#### [Introduction to Outcome Based Security Contracts](https://www.youtube.com/watch?v=XsMdr5I6mDE)
> have you ever wondered how Security Contracts can be more efficient and effective today we dive into the world of outcome-based Security Contracts these contracts represent a shift in the security industry focusing on the results rather than the number of resources allocated they are pivotal in creating a vibrant technologically advanced and competitive security industry but how do we get there in February 2018 the security industry transformation map or itm was launched the itms vision is to rely Less on Manpower and more on technology transforming the industry From the Inside Out the progress is evident with increasingly more outcome based Security Contracts being implemented outcome based Security Contracts are a step towards achieving this Vision providing more productive solutions tha...

### More Videos
- **[Scaling Smart Contract Security with AI I Shashank](https://www.youtube.com/watch?v=4KOnWs01vUE)**
  _Shashank, founder of SolidityScan, explains how AI and automation are transforming smart contract security. With over 14 years in cybersecurity (credited with finding bugs in Apple, Google, and Fac..._
- **[Beyond the Surface: Understanding Different Types of Vulnerability Scans](https://www.youtube.com/watch?v=LGfIB9j1vwo)**
  _Confused about the different types of vulnerability scans? In this episode of the HIPAA Insider Show, we explore how system scanning and vulnerability scanning tools work, what they detect, and why..._
- **[Smart Contract Auditors vs AI: Who's Here to Stay](https://www.youtube.com/watch?v=C_orWHTGTbo)**
  _Welcome to another Web3 security tutorial! In this video, we'll see and test whether AI can replace smart contract auditors and explore a tool, which can enhance your auditing process with the help..._
