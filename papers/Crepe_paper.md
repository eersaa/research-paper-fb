# Crepe: A Mobile Screen Data Collector Using Graph Query

**Authors:**
Yuwen Lu (University of Notre Dame), Meng Chen (UC Berkeley), Qi Zhao (University of Maryland, Baltimore County), Victor Cox IV (University of Notre Dame), Yang Yang (University of Notre Dame), Meng Jiang (University of Notre Dame), Jay Brockman (University of Notre Dame), Tamara Kay (University of Pittsburgh), Toby Jia-Jun Li (University of Notre Dame)

**Conference:** CHI '26, April 13–17, 2026, Barcelona, Spain
**DOI:** https://doi.org/10.1145/3772318.3791137

---

[FIGURE 1]
*Figure 1: The Crepe app provides a low-code solution for academic researchers to collect data displayed on mobile screens. Through a programming by demonstration paradigm, a researcher taps on the target data to collect on the screen (A). Crepe will automatically generate a Graph Query we designed (B) that can accurately identify and locate the target UI element. When seeing new screens, the Graph Query will be executed on the screen's UI Snapshot (C) and identify the UI element containing our target data. The created Graph Query will be shared with data collection study participants to collect the target data on other screens (D).*

---

## Abstract

Collecting mobile screen information datasets remains challenging for academic researchers. Commercial organizations often have exclusive access to mobile data, leading to a "data monopoly" that restricts academic research and user transparency. Existing open-source mobile data collection frameworks primarily focus on mobile sensing data rather than screen content. We present Crepe, a no-code Android app that enables researchers to collect information displayed on screen through simple demonstrations of target data. Crepe utilizes a novel Graph Query technique, which augments mobile UI structures to support flexible identification, location, and collection of specific data pieces. The tool emphasizes participants' privacy and agency by providing full transparency over collected data and allowing easy opt-out. We designed and built Crepe for research purposes only and in scenarios where researchers obtain explicit consent from participants. Code for Crepe will be open-sourced to support future academic research data collection.

## CCS Concepts

- Human-centered computing → Ubiquitous and mobile computing systems and tools
- User interface management systems

## Keywords

Mobile data collection, Graph Query, UI understanding, Data transparency, Android accessibility, End user programming

---

## 1 Introduction

To research on mobile information consumption and behavior, researchers often analyze screen data on users' mobile interfaces. Such data serves as a window into recommendation algorithms and how people interact with technology in everyday lives. Unlike traditional mobile sensing data that captures device states and sensor readings, screen information represents what users actually see and engage with, making it an invaluable resource for understanding the user side of interactions.

However, collecting mobile screen data has remained difficult for academic researchers. In practice, access to mobile app usage data is often controlled by smartphone platforms like iOS and Android, or by individual app developers who guard their user data closely. Academic researchers find themselves in a challenging position: they have to either rely on limited public developer APIs, which are subject to arbitrary corporate policy changes, or negotiate complex collaborations with commercial organizations that may compromise research independence. This "data monopoly" creates barriers to empirical mobile research.

While many open-source mobile data collection frameworks exist to support academic research, most solutions focus on mobile sensing data (e.g. accelerometer, gyroscope, luminance) rather than the screen information that users see and interact with. The technical challenge lies in reliably and automatically identifying which user interface screens contain target data, then locating and collecting that specific information. Current approaches often require users to actively input data or upload screenshots manually, or they continuously record user screens, an approach that is both inefficient and raises serious privacy concerns.

In this work, we ask: **how can we support mobile screen data collection for academic researchers, while respecting user privacy and maintaining data quality?**

We created Crepe, a novel Android data collector that embodies a programming-by-demonstration approach to mobile screen data collection. At its core, Crepe introduces **Graph Query**, a query language that augments mobile UI screen structures to support flexible identification, location, and collection of specific data pieces. Graph Query helps when researchers want to collect only specific pieces of screen information, instead of full screens all the time. With Crepe, researchers can define what data to collect through simple, no-code demonstrations, while participants maintain full transparency and control over their data through intuitive privacy controls and real-time collection feedback.

We designed Crepe with participant agency at its center. Users see exactly what data is being collected through semi-transparent overlays and dedicated data pages, and they can leave any study at any time by simply removing the collector from their app. This approach transforms mobile data collection from an opaque, researcher-controlled process into a transparent, participant-empowered collaboration.

To evaluate Crepe, we conducted a series of three user studies with both researchers and participants, uncovering performance characteristics, limitations, and future directions in both laboratory and real-world settings.

In all, our contributions include:

1. A novel query language, **Graph Query**, to reliably identify, locate, and collect target data on UI screens;
2. **Crepe**, the first Android data collector app to support flexible, customizable, low-code UI screen data collection using programming by demonstration (PBD);
3. A series of three user studies demonstrating Crepe's effectiveness in empowering both researchers and participants in mobile screen data collection.

> *Crepe is an acronym for "Collector for Research Experiments of Participant Experiences". Crepe is open source at https://github.com/ND-SaNDwichLAB/crepe.*

---

## 2 Background and Related Work

### 2.1 Understanding Human Activities via Mobile Data

Mobile devices, especially smartphones, are ubiquitous in people's everyday lives. Mobile applications make use of various information about user social activities, which are embedded in users' interactions, app usage patterns, and preferences. As a result, researchers in HCI and social science have been leveraging rich data gained from mobile apps to improve user experiences, uncover societal trends, and understanding user behaviors and attitudes.

Screen data from mobile phones, i.e. information displayed on mobile screens, are particularly valuable for understanding user behavior and preferences. Screen data capture visual information and layout of the apps, providing insights into how users navigate and engage with different features. By analyzing this rich, granular data, researchers can gain a deeper understanding of user needs, preferences, and pain points, which can inform the design of more user-friendly and engaging mobile experiences.

#### 2.1.1 Analyzing Behavioral Data Streams

Researchers from diverse backgrounds, such as social science or business, mine mobile data for behavioral patterns and insights. Experience Sampling Method (ESM) is a research methodology to obtain in situ data for constructing an understanding of subjects' daily behaviors, feelings, and thoughts of participants. In the survey conducted by Berkel et al., smartphone-based ESM benefits researchers in improving data quality through validation, collecting rich multimodal data for context reconstruction, and enabling real-time data collection and analysis. ESM can provide social scientists with combined human and sensor data in addition to background logging. Aside from sensor data, ESM questionnaires can also capture external aspects of experience, such as time, place, activities, and companion. For instance, Yue et al. adopted ESM to study the function of photos. They found that photos can be used to trigger memory during follow-up interviews and as a beneficial component in data analysis. In this work, our goal is to create a low-code mobile UI screen data collection tool. Our app Crepe can facilitate academic researchers to instrument screen data collections without the need to extensively develop customized data collectors, or have public access to data APIs.

### 2.2 Computational Understanding of Mobile UI Structures and Data

Technical researchers have developed intelligent systems that achieve computational understanding of mobile user interfaces. Sugilite, a mobile PBD system that the execution of various tasks through user-driven multimodal direct manipulations, parses UI elements and layout information to understand the intentions contained in user activity. The Sugilite system leverages the accessibility API of Android to encapsulate high-quality relevant behavioral data on mobile devices. UI understanding and summarization is another topic that HCI researchers are interested in. An accurate and succinct description of UI semantics can facilitate seamless interactions as well as bridge the gap between language and user interface. Prior research such as Screen2Vec and Screen2Words, adopted Machine Learning (ML) techniques to support UI design. More recent approaches have also leveraged the advance of Large Language Models (LLMs) and large multimodal models to enhance conversational interactions on mobile UI. In this work, with our proposed novel Graph Query, we aim to create a deterministic and reliable query language that can reliably and deterministically identify and locate a piece of target information on screen. This compliments existing research on mobile UI understanding in addition to existing deep-learning-based mechanisms.

Crepe is built on Android Accessibility Service API, which provides a universal, framework-agnostic representation of UI elements across diverse Android app development approaches. While Android applications can be built using various frameworks including native Android Views, React Native, Flutter, Jetpack Compose, the Accessibility Service transforms all of these into a standardized accessibility tree composed of `AccessibilityNodeInfo` objects. This abstraction layer is required by Android guidelines to support, regardless of their internal rendering mechanisms. This enables Crepe to collect data uniformly across native apps, hybrid apps, and web content using the same Graph Query mechanism. Applications that fail to properly implement accessibility support (e.g., canvas-based games, poorly implemented custom views) may have limited `AccessibilityNodeInfo` data, as we will discuss in Section 3.2.7.

### 2.3 State-of-the-art Mobile Data Collection Tools

A variety of data collection tools and frameworks have been proposed to support academic data collection of various types of data. **Aware** is a mobile instrumental tool designed for collecting usage context through sensors on mobile devices. Rather than being a simple mobile data collector, Aware creates a collaborative framework for researchers to share context data with the community. The **Stanford Screenome project** built a tool to take screenshots of users' phones at a set interval. **Purple Robot** is an extensible and modular development platform that supports behavioral and clinical intervention. The tool enables Behavioral Intervention Technology (BIT) stakeholders to create mobile apps that collect user management, content authorship, and content delivery data, through which physician-scientists can evaluate and share data resources to increase knowledge finding and generalization. **ShiptCalculator** is a research tool designed to track and share workers' aggregated data about their pay to empower workers in offering awareness of wage transparency and advocacy to campaigns. In the data collection process, workers send screenshots of their pay history to ShiptCalculator, which parses them using OCR and stores structured data. The system then sends a validation text to workers and allows them to explore their pay details.

However, no current tool supports the flexible and specific collection of data displayed on mobile UIs based on our review of previous work. A related technique is **XPath**, a widely-used query language for selecting nodes in XML and tree-structured documents based on structural relationships (parent/child, siblings, ancestors). However, XPath is limited to defining document tree relationships, and is limited in expressing visual or spatial relationships as elements appear on the rendered screen. XPath also requires a fair amount of technical expertise to write the query language. In addition, a recent relevant work presents a tool that captures all screen text from Android smartphones. While researchers can specify which apps to collect from, the tool lacks element-level specificity. Their tool collects all text displayed within those apps rather than targeting specific data pieces. This creates additional filtering burden for researchers interested in targeted within-app data. Moreover, their validation assessed data patterns and completeness without comparing against a rigorously labeled ground truth baseline. In general, either of these techniques handles data collection tasks such as "collect all Uber prices the user requested" or "collect all Instagram ads the user saw". Our design of Crepe aims to solve these limitation, through a programming by demonstration (PBD) interaction paradigm and our design of Graph Query.

---

## 3 Proposed Method

Our goal for the Crepe data collector is three-fold. First, we seek to empower researchers lacking programming expertise to easily create and deploy data collections. Second, we prioritize the privacy and agency of individual data collection participants. Lastly, we also want to address the following observed technical challenges in reliable mobile screen data collection, which hinder even technical researchers:

1. The difficulty in automatically detecting that target data showed up on screen;
2. The lack of precision in locating target data and accessing its content;
3. The limited generalizability for dynamically changing data content.

To solve these challenges, previous collectors have asked participants to either directly input target data or upload screenshots or screen recordings containing target data. However, these practices significantly increase participants' efforts and reduce the reliability of the collected data's quality.

In contrast, in Crepe, we used a novel Graph Query technique to address the above challenges. Graph Query has the following characteristics:

1. Triggering a data collection only when the target data shows up;
2. Locating and accessing only the target data on screen;
3. Generalizing easily to diverse data types, especially dynamically changing data.

For the rest of this section, we first give an overview of the experience design of Crepe, our Android mobile data collection app. Then, we dive into the technical details of the novel Graph Query we designed and implemented as the backbone of Crepe.

### 3.1 The Crepe Data Collector User Experience

The Crepe data collector has two main target user groups: researchers who want to instrument a mobile data collection study, and study participants who want to contribute mobile data to ongoing data collections.

Researchers have two main tasks when using Crepe (Figure 2): creating a collector (A), and sharing collectors with study participants (B). A researcher can use Crepe's graphical user interfaces to define the start and end dates of a collector, as well as the target app to collect data from.

The most important yet trickiest step in defining a data collector is specifying the target data on screen to collect. In Crepe, our design goal is to minimize the complexity of this specification process for researchers, by only asking them to tap on the screen data to collect in the target app, and describe their intention to collect these data (Figure 2 A). Crepe automatically translates these two pieces of information into a formal, executable Graph Query, which includes information about the target data's parent app package, component type, and relations with other UI entities on screen. This Graph Query is the core of a data collector and will be used to reliably identify and precisely locate target data on the study participants' devices. This specification process follows a programming-by-demonstration paradigm and provides a simple, no-code experience for researchers to specify the target data. After the target data are specified and descriptions are added, a collector is created. Afterward, the researcher can copy and share the unique ID of this collector with participants (B). The collector will run on the participants' device for the specified data collection periods. Afterwards, the researcher can receive the data collected in a self-defined database (E) and analyze it to uncover research insights (F). Our initial implementation of Crepe transmits collected data to a pre-configured Google Firebase Realtime Database that encrypts data both in transit and at rest. We plan to support researchers' customized configuration of their own database servers in the future.

For study participants, they can easily add a collector to Crepe by entering the unique collector ID shared by the study's researchers (C), using Crepe's graphical user interfaces. After granting Crepe with the necessary Android Accessibility Service permission, the added collector(s) will start automatically running in the background of the participants' devices (D). Guided by the Graph Queries associated with the participants' added collectors, Crepe will selectively seek the appearance of target data exclusively when the designated target apps are active. Once the target data is detected, Crepe will scrape and transmit the relevant information to the researchers (E). The participant will be able to monitor the active status of the collector(s) they have joined in Crepe. To drop out of a study, participants can simply delete a collector from their Crepe app, and the collector will no longer run in the background.

**Data collection transparency.** Ensuring a transparent communication of data collection is critical in our design of Crepe. We ensure participants have the full control over their participation status and data contributions using two main measures. First, we adopt an "opt-in" participation mechanism, where participants actively add collectors to their Crepe app to join data collections. We intend this to be combined with the explicit consents that researchers must obtain before each data collection study starts. Second, each participant can opt out of any collection, at any time, by deleting the collector from their Crepe app, which will immediately terminate the collection on their mobile devices.

We also prioritized data collection transparency in Crepe design (Figure 3). Every time data is collected from the user's screen, a semi-transparent yellow highlight will appear over the collected data every time (1). We also designed a dedicated screen to show the users all of the data collected (2). We will also continuously release new privacy-centric features, such as daily or weekly push notifications summarizing data contributions, and the ability to request all their data be deleted when they withdraw from a study.

---

[FIGURE 2]
*Figure 2: The workflow of Crepe for our main user groups: data collection researchers and participants. Researchers create a new data collector by demonstration (A) and share the collector ID with participants (B). Participants add the collector to their own devices (C), which runs in the background to collect the specified target data (D). Note that in step D, Crepe uses Android Accessibility Service to access the view hierarchy of the current UI screen, then processes the view hierarchy, instead of directly working with screenshot images. The collected data is transmitted to a database (E) for the researcher to analyze and gain insights (F). The colors in the background indicate each user group's experience involved in the holistic Crepe pipeline.*

---

[FIGURE 3]
*Figure 3: Two design features that enhance data collection transparency for system users (data contributors). When the system operates in the background, a yellow highlight appears over the collected content at each time of collection (1). Additionally, we designed and implemented a page that displays all collected data organized by collector, allowing users to review their contribution history and details (2).*

---

### 3.2 Graph Query

#### 3.2.1 Building blocks of Graph Queries: screen entities and their relations

We develop a novel Graph Query in Crepe for accurate and consistent extraction of various types of screen information (Figure 4). The intuition behind Graph Query is to *uniquely* identify the element(s) that contain the target data using (1) the UI elements' own attributes and (2) relations with other elements on screen. Graph Query builds on top of the XML mobile screen hierarchy from Android Accessibility Service, similar to the DOM tree of web HTML. This mobile screen hierarchy contains Views on the current screen (Figure 4, 1), each of which contains rich properties including content, screen location, etc.

First, we enhance the default mobile screen hierarchy provided by Android Accessibility Service into an augmented **UI Snapshot**, which contains additional relations between screen entities (Figure 4, UI Snapshot section). We defined a *screen entity* to be either an UI element (i.e., Android View) or an attribute of the UI element, in data representations such as strings or integers. The relations between these screen entities include:

1. UI elements to their own Android implementation attributes (e.g., `hasClassName`, `hasScreenLocation`, `isEditable`);
2. UI elements to their semantic content (e.g., `hasText`, `containsEmailAddress`, `containsMoney`, `containsDate`);
3. Hierarchical relations between UI elements in the XML screen hierarchy (e.g., `hasParent`, `hasChild`, `hasSibling`);
4. Spatial relations between UI elements based on their rendered screen locations (e.g., `right`, `left`, `above`, `below`, `near`).

Table 1 provides a comprehensive list of the main screen metadata and element relations used to construct Graph Queries, organized by category, deprioritization status, and example use cases. Spatial relations are computed from UI elements' bounding box coordinates, enabling queries like "the price text left of the quantity input field". Semantic relations automatically parse structured data from text (e.g., extracting $12.50 as a numeric price). In the future, this set of relations can be *extended*, i.e. researchers can define custom relations for domain-specific needs (e.g., `hasStarRating` for review collection, `containsHashtag` for social media analysis). The priority of attributes are empirically decided through trial and error, with the goal as getting the most generalizable Graph Query candidate that can flexibly and accurately collect the target data across different screens (more details in Section 3.2.4).

These relations comprehensively encapsulate the various relations and semantic contents that are useful for identifying and locating a date on screen. With such additional information, an UI Snapshot is a collection of subject-predicate-object triples denoted as (s, o, p), where s and o are two entities and the p is the relation between s and o.

#### 3.2.2 Automatic generation of Graph Queries

When a researcher demonstrate the target data to collect by tapping on it (e.g. tapping on "apple" on the screen in Figure 4 Step 1), we locate the associated UI element in the UI Snapshot, and utilize a unique set of its characteristics in the UI Snapshot to generate Graph Query candidates (Figure 4, Step 2). The Graph Query can be connected via 3 logical operators: `conj` (and), `or` (or), and `prev` (previous). We defined a set of context-free grammars, summarized in Table 2, to construct formal Graph Queries based on screen entity relations in UI Snapshots.

The context-free grammar (CFG) in Table 2 defines how Graph Queries are systematically constructed from screen entity relations in UI Snapshots, similar to how CFGs are used in compilers to parse programming language syntax. The base case `E → e` represents a single UI entity, while the rule `S → (join r E)` combines an entity with a relation (e.g., `(hasText "Sponsored")`), and `S → (and S S)` chains multiple conditions using logical operators (`conj`, `or`) or spatial/hierarchical operators (`above`, `hasParent`). The aggregation rules `T → (ARG_MAX r S)` and `T → (ARG_MIN r S)` enable selecting entities based on numeric properties, such as `argmin hasListOrder` to find the first list item. These grammar rules ensure any valid Graph Query, from simple matches like `(isClickable true)` to complex nested expressions like `(above (conj (hasText "Sponsored") (hasClassName "Button")))`, can be systematically constructed, parsed, and executed across different screens. As a result, Graph Queries encapsulate combinations of the screen entity relations for the target UI element and Crepe creates combinations can uniquely identify *only* the target UI element on screen (Figure 4, Step 2). The combinations of screen entities are empirically set through experimentation. All Graph Queries will have `hasPackageName` and `hasClassName` to establish the context. In most cases, more than one Graph Query can uniquely locate the target UI element on the screen.

#### 3.2.3 Graph Query Generation Walkthrough

To illustrate the above technical steps in detail, here we map out the steps involved in generating a Graph Query through a detailed example, in complement to Figure 4.

Note that the above query examples are simplified for easier understanding. Please refer to the Graph Queries in Table 2 for real example Graph Queries.

#### 3.2.4 User Intent Disambiguation: Selecting the Best Graph Query

As described above, for each target data, Crepe generates a few Graph Query candidates that can each uniquely match the target data. However, some query candidates are more generalizable to other screens: for example, to collect Instagram story ads, a query that collects the text above "Sponsored" is more likely to collect all target data, than a query that collects text that shows up at a specific screen location (the first and third queries in Figure 4, Step 2). As a result, we empirically defined UI element attribute priorities and used a set of heuristics to rank the generalizability of generated queries (Table 1). Yet, from our user studies, we realized that it is best to adopt a human-in-the-loop process, engaging the researcher in this selection process.

Through iterative design with researchers (details in Section 4.2) and taking inspirations from past research, our final design presents the top Graph Query candidates in natural language phrases for the user to select from. We translate Graph Queries into natural language phrases, such as "the UI element above the Button that says Sponsored", to show to the user instead of its original query language form (Figure 4, Section 2, option 1). We translated the Graph Queries so that the researchers, especially the non-technical ones, are not exposed to unnecessary technical details of Crepe. We translate the Graph Queries using a large language model. This ensures the selected Graph Query best reflects the researcher's data collection goals.

> *We used GPT-3.5-turbo in our implementation due to its ease of access, short inference time, and empirically high-quality outputs observed on our task. Our prompt can be found in Appendix A.1.*

#### 3.2.5 Graph Query execution on UI Snapshots: retrieving the target data

After a Graph Query is created, it can be used to collect target data on any UI Snapshot with elements sharing the same set of entity relations. In the background, Crepe runs the Graph Query every time a UI Snapshot is updated from changes in screen content (Figure 4, Section B). We limit the Graph Query to only run in the target app package, in order to effectively reduce unnecessary battery usage of Crepe. After identifying and locating the target UI element on screen (Step 3), Crepe can collect the target data to collect through the element's attributes such as text and content description.

#### 3.2.6 Summary

Graph Query showcases three major strengths in screen data collection. First, the data collection mechanism using Graph Query is *fully deterministic* and thus much more *reliable* than alternative solutions like using Optical Character Recognition (OCR) or deep-learning based detection models. Second, Graph Query provides much more flexibility in identifying and locating target UI elements through their implementation attributes, semantic content, hierarchical screen structure position, and screen location relations (Section 3.2.1). For instance, a researcher can utilize the pre-defined `hasPrice` relation to collect Uber drivers' task payment information, a common task on gig worker support platforms. In the future, developers can also extend existing entity relation types for more customized data collection tasks. Lastly, by utilizing Android's Accessibility Service, using Graph Query can easily integrate the collection of user interaction data, a feature included in Crepe yet unsupported in most vision-based data collection tools. In the future, Crepe can be extended to collect more rich media information such as screenshots under the study participants' consent.

---

**Table 1: Main screen element metadata and relations used to construct Graph Queries.** Accessibility API metadata are directly retrieved through Android Accessibility API, while the others were computed by Crepe. These computed attributes enable our Graph Queries to express the semantic, structural, and spatial information of target screen data. We deprioritize relations that are less generalizable across screens, such as fixed screen coordinates and Android Resource IDs, but still use them as necessary fallbacks.

| UI Element Attribute | Category | Deprioritized | Description |
|---|---|---|---|
| **Accessibility API metadata** | | | |
| `hasPackageName` | Implementation | No | Ensure query runs in target app only |
| `hasClassName` | Implementation | No | Filter by widget type (Button, TextView) |
| `hasText` | Semantic | No | Locate element by displayed text |
| `hasContentDescription` | Semantic | Slightly | Use accessibility labels for identification |
| `isClickable` / `isEditable` / `isScrollable` | Implementation | Slightly | Filter by interaction capabilities |
| `hasViewId` | Implementation | Yes | Identify by Android resource ID (may change, thus deprioritized) |
| `hasScreenLocation` | Implementation | Yes | Fixed coordinates (fragile across devices) |
| **Semantic Content Relations (Computed)** | | | |
| `containsMoney` | Semantic | No | Extract prices, wages (e.g., turning "$12.50" string into a numerical value of 12.50) |
| `containsDate` / `containsTime` | Semantic | No | Parse temporal information for tracking |
| `containsPhoneNumber` / `containsEmailAddress` | Semantic | No | Extract contact information |
| `containsNumber` | Semantic | Slightly | Generic numeric data extraction |
| `containsPercentage` / `containsTemperature` | Semantic | Slightly | Domain-specific numeric parsing |
| **Hierarchical Relations (Computed)** | | | |
| `hasParent` / `hasChild` | Hierarchical | No | Navigate view hierarchy (e.g., list items) |
| `hasParentText` / `hasChildText` | Hierarchical | No | Identify element by parent/child content |
| `hasSiblingText` | Hierarchical | Slightly | Use adjacent elements as context |
| `hasListOrder` | Hierarchical | Slightly | Locate nth item in scrollable lists |
| **Spatial Relations (Computed)** | | | |
| `above` / `below` / `left` / `right` | Spatial | No | Locate relative to landmark elements |
| `near` / `nextTo` | Spatial | Slightly | Proximity-based identification |

---

**Table 2: Context-free grammars (CFGs) for constructing Graph Query in Crepe.** Q denotes the initial non-terminal symbol, terminal e denotes a GUI object entity, and terminal r denotes a relation. Other non-terminal symbols are employed for intermediary steps in the derivation process.

| Expression | Rule |
|---|---|
| E | → e |
| E | → S |
| S | → (join r E) |
| S | → (and S S) |
| T | → (ARG_MAX r S) |
| T | → (ARG_MIN r S) |
| Q | → S \| T |

---

[FIGURE 4]
*Figure 4: The detailed process of Graph Query generation and execution in Crepe. Section A shows how to generate a Graph Query: Crepe first uses Android Accessibility Service to access the view hierarchy of a UI screen (1) and augment it into a UI Snapshot graph, using UI elements' characteristics and their relations. To identify the target UI element within the UI Snapshot graph, Crepe combines a set of UI element characteristics on this UI Snapshot to uniquely identify the target UI element on this UI Snapshot. We put these characteristics together to construct our Graph Query (2) and rank them based on their flexibility. In Section B, step (3) depicts the execution of a chosen Graph Query on two new screens, one containing the target data and one not. The set of unique characteristics of the target UI element ensures we only successfully collect the target data in "duecelove", but not on the other screen.*

---

[FIGURE 5]
*Figure 5: A walkthrough example demonstrating how Crepe constructs a UI Snapshot and generates Graph Queries. Starting from raw accessibility data, the system augments the UI structure with spatial relations and produces candidate queries that can locate target data across different screens. Queries that are more generalizable, for example, those that are based on more stable anchor points (e.g., the "Sponsored" button) are ranked higher.*

**Example: Collecting Instagram Ad Advertiser Names**

*Scenario:* A researcher wants to collect advertiser names from Instagram story ads (e.g., "apple", "nike"). The advertiser name appears as text above a "Sponsored" button.

*Step 1 - Accessibility Service captures screen:* When the researcher taps on "apple", Android Accessibility Service provides the view hierarchy, containing relevant nodes including:
- TextView (text="apple", className="android.widget.TextView", bounds=[10,100][200,150])
- Button (text="Sponsored", className="android.widget.Button", bounds=[10,160][200,200])

*Step 2 - Augmentation into UI Snapshot:* Crepe converts this into triples, adding computed spatial relations:
- (node_1, hasText, "apple")
- (node_1, hasClassName, "android.widget.TextView")
- (node_1, hasScreenLocation, Rect[10,100][200,150])
- (node_2, hasText, "Sponsored")
- (node_2, hasClassName, "android.widget.Button")
- (node_1, above, node_2) ← computed from UI element bounding boxes

*Step 3 - Query Generation:* Crepe creates candidate queries that uniquely match node_1, using the Context Free Grammar defined in Table 2:
- **Query 1:** `(above (conj (hasText "Sponsored") (hasClassName "Button")))` — in natural language means: "Text above the button that says 'Sponsored'"
- **Query 2:** `(conj (hasScreenLocation Rect[10,100][200,150]) (hasText "apple"))` — in natural language means: "Text 'apple' at screen location (10,100)"

Query 1 is ranked higher due to better generalizability (spatial relations vs. fixed coordinates). When executed on new screens, Query 1 successfully collects "nike", "adidas", etc., while Query 2 would fail if advertisers appear at different screen locations. This example also illustrates an important idea in Graph Query: for dynamically changing content, it is often easier to find an "anchor point" that does not change often (in this case, the button with text "Sponsored").

---

#### 3.2.7 Limitations and Extensibility

Graph Query's relational encoding provides robustness to many challenges in mobile data collection, as long as the semantic, hierarchical, and spatial structure defined in the query is preserved. Our main assumption is that even across app updates and redesigns, major semantic information and screen structures are likely to be preserved for consistent user experience. However, we acknowledge that certain app redesign and localization changes might limit our Graph Query's generalizability. Table 3 summarizes scenarios where Graph Query faces challenges and potential mitigation strategies. In general, the Graph Query language is designed as a set of composable primitives rather than fixed templates for data collection. In fact, in our evaluation study (Section 4.3.3), we encountered the limitation of changing anchors for Instagram stories. We were able to work around it by demonstrating the target data in multiple potential layouts.

---

**Table 3: Limitations of Graph Query and potential workarounds.** This table shows a list of potential cases where Graph Queries might not handle well. For cases where one Graph Query cannot comprehensively capture all potential structures, we designed Crepe to support multiple Graph Queries, allowing researchers to handle localization changes (e.g., RTL/LTR layouts) and varying app designs across A/B testing or different devices.

| Limitation | Description and Potential Workarounds |
|---|---|
| Localization that changes layout direction | Graph Queries using spatial attributes such as left/right may break; researchers need to add multiple Graph Queries to cover different layout scenarios if they consider cross-cultural data collection needs |
| Broad, underspecified collection needs | For example, "collecting all ads users see on their phone". Researchers must demonstrate each data to collect specifically; Crepe then creates separate queries for each demonstrated scenario |
| Dynamically generated content with no stable anchors | For example, infinite scroll feeds with no headers. Researchers may use `hasListOrder` with argmin/argmax to systematically collect items; may require demonstration of multiple examples to establish pattern |
| Canvas-based UI elements (e.g., game graphics, custom-drawn charts) | Android Accessibility Service can be limited for canvas content; researcher can extend Crepe to include screenshot capabilities to handle these scenarios |
| Non-text rich media analysis (images, videos, audio) | Screenshot API available for image capture; can extend with computer vision or audio transcription modules for content analysis |

---

### 3.3 Implementation

Crepe was implemented using Android, Google Firebase Realtime Database, OAuth, and OpenAI API. Note that we only used OpenAI large language model for Graph Query translation (Section 3.2.4) and the whole data collection process does not involve any deep learning. The app was developed in Java using Android Studio and is compatible with mobile devices running Android 9.0 or above (around 95.4% of the Android mobile phone market as of February 2025). Firebase Realtime Database was selected due to its high-standard data encryption both in transit and at rest, real-time data synchronization, and reliable user authentication. However, we recognize that Firebase might not serve all data collection and compliance needs; since we will open source Crepe, researchers have the full customizability of desired database provider and storage location (see deployment options below).

To implement the query language, Crepe uses the Android Accessibility Service and captures Accessibility Events as a result of changes in the content of the screen. The captured Accessibility Event contains the new UI screen hierarchy. Android Accessibility Service gets triggered frequently as screen content changes (potentially many times per second), so it is necessary to avoid duplicate query execution and data collection, for optimized battery consumption and data storage. In our implementation, we prevent collecting duplicate data through two main mechanisms: (1) content-based deduplication using a HashSet to track recently collected results, and (2) a 4-second throttling interval to prevent duplicate saves. To allow re-collection of legitimately reoccurring content (e.g., when users scroll back to previously viewed screens), we clear the deduplication cache every 10 seconds. As a result, this strategy balances collection efficiency with completeness.

The code for Crepe will be open-sourced to enable easy adoption and community-supported improvements.

### 3.4 Open Sourcing and Deployment Options

Crepe will be fully open-sourced, offering complete customizability and self-hosting options for specific research and regulatory needs. While our reference implementation uses Firebase Realtime Database, the data collection architecture is built on a modular API layer that can be adapted to work with any backend infrastructure. Researchers can deploy Crepe with self-hosted databases (e.g., MongoDB, PostgreSQL) or cloud services that meet their institutional requirements.

The ability for everyone to self-host Crepe is particularly important for studies with sensitive data or regulatory constraints, as different countries and territories have specific requirements about data storage location and cross-border data transfer. Standard Firebase may not meet certain compliance requirements (e.g., FERPA, HIPAA, GDPR), but enterprise configurations or alternative infrastructures can address these needs. We encourage researchers to consult with their institutional review boards and IT security teams when deploying Crepe to ensure compliance with relevant data protection regulations.

---

## 4 Evaluations

To test and validate Crepe, we conducted a series of three evaluation studies. The first two studies focused on researchers' experience to collect data (Study 1) and Crepe's data collection accuracy (Study 2). The third study investigated Crepe's battery usage and perceived interruptions in the wild for participants (i.e. data contributors) (Study 3). The first two studies were designed to be in-lab, while Study 3 was conducted as a field study. These three studies together aim to answer the following research questions:

1. **RQ1:** How well does Crepe support researchers in collecting mobile screen data (Study 1)?
2. **RQ2:** How accurately does Crepe collect target data on participants' screens (Study 2)?
3. **RQ3:** How does Crepe influence device performance for participants (i.e. data contributors) in a real-world data collection scenario (Study 3)?

### 4.1 Evaluation Scenarios

We wanted our performance evaluation of Crepe to cover a range of different data collection needs. Looking broadly into previous research in HCI, CSCW, and Data Science, we extracted three scenarios where researchers can use Crepe to collect user screen data. Our evaluation studies were based in these scenarios.

**Scenario 1: Instagram Story Advertisements.** Instagram Story advertisements are sponsored short image/video segments that appear between an Instagram user's following content. They usually come with a "Sponsored" label to be distinguished from users' regular following content. Multiple research studies have been conducted in recent years around Instagram Story advertisements, to understand how users perceive and understand this specific form of advertising. However, it is not easy to collect a dataset of Instagram story advertisements.

Getting access to a dataset of Instagram's Story ads can enable research contributions in fields including social media research, algorithm auditing, and usable privacy. Specifically, we can empirically observe users' interactions with Instagram Story ads, as well as inferring dwelling time over Story ads based on the first and last content change while a specific ad appears on screen. More generally, some broader questions we can answer with the dataset include: What empirical understanding of Instagram's personalized advertisement algorithms can we obtain from quantitative data analysis? How do Instagram Story advertisements reveal the platform's portraits of individual users' preferences? And what are users' folk theories of Instagram's personalized ad algorithm?

**Scenario 2: Uber Pricing.** Ride-sharing platforms like Uber implement dynamic pricing strategies that adjust fare prices based on various factors including demand, time of day, and location. Collecting real-time price data for trip requests would allow researchers to study pricing algorithms, examine fare consistency across different user groups, and analyze how external factors influence ride-sharing costs. Previous research has attempted to understand these pricing mechanisms through qualitative measure and quantitative analysis. However, current data sources cannot cover many user-specific aspects such as price variations across user groups and discount information. This data could help researchers investigate questions about algorithmic fairness in transportation access, analyze the relationship between surge pricing and local events, and study how pricing strategies affect user behavior in different geographical and temporal contexts. In our scenario, we focus on collecting the pricing information for participants' Uber ride requests.

**Scenario 3: Chrome Browser Discover Feed.** Mobile browsers like Google Chrome integrate algorithmic news feeds into their search interface. These algorithmic feeds, often supported by deep learning, curates content based on users' browsing behavior and inferred interests. These algorithmic feeds, while work at an individual user level, have wide and profound social implications. Using Chrome as an example, accessing its Discover feed data from the user's perspective enables research in algorithm auditing, helping to analyze content recommendation patterns, assess personalization mechanisms, and identify potential biases. Researchers have proposed audit studies to uncover discriminatory practices. Researchers can investigate how these algorithms shape information exposure by examining content diversity, frequency, and source representation. Understanding these dynamics in the Discover feed can identify biases impacting users' information access and inform design improvements for more equitable content curation.

---

[FIGURE 6]
*Figure 6: We identified three potential usage scenarios of Crepe for our evaluation. Scenario 1 collects the advertiser information in Instagram Story ads, scenario 2 collects Uber ride pricing when user requests a ride, and scenario 3 collects the top feed item in Chrome Discover Feed recommendations. Crepe shows a yellow highlight overlay every time the target data is collected, providing full transparency to the collection participants.*

---

### 4.2 Study 1: Evaluating Crepe Usability with Researchers (In-Lab)

Study 1 evaluates how Crepe effectively supports **researchers**. While Crepe serves both researchers (collector creators) and users (data contributors), this study focuses specifically on the researcher experience during collector creation. We examine the usability of our Programming By Demonstration (PBD) approach in creating a data collector and try to understand what are researchers' potential use cases of Crepe.

#### 4.2.1 Procedure

Each one-hour session began with a brief introduction to Crepe's motivation and core features. Participants then created data collectors for three representative usage scenarios (detailed in Section 4.1) using Crepe's interface. After completing the tasks, participants completed a modified System Usability Scale (SUS) questionnaire, including five-point Likert scale questions evaluating Crepe on its usability and utility for future research projects. We concluded with semi-structured interviews exploring participants' envisioned uses of Crepe in their research. All studies were carried out in person and participants received a $15 digital gift card for their time. To evaluate the accuracy of the PBD-generated Graph Queries, two authors independently analyzed whether each Query correctly captured the researcher's specified data collection targets.

#### 4.2.2 Participants

We recruited 5 HCI researchers through social media advertisements and word of mouth. All participants had experience with data collection and had interests in collecting users' screen data for research purposes. Most participants have experience collecting various types of user data in the past (see participant demographics in Appendix A.2).

#### 4.2.3 Results

The usability evaluation showed positive results (Figure 7), with participants rating Crepe favorably on all questions. Most participants also showed a strong interest in using Crepe for future screen data collection studies and think it would not require much adaptation to Crepe.

In Study 1, as researchers created data collectors using Crepe, we also evaluated the programming by demonstration (PBD) pipeline for authoring candidate Graph Queries. Our evaluation was carried out on in total 15 created collectors (3 example scenarios for each of the 5 participants). We found that in all of the 15 occasions (15/15, 100%), our PBD pipeline successfully generated Graph Queries that correctly match users' data collection goal (see Figure 4). Based on participant feedback, we iteratively improved the design of the user disambiguation process. We landed on our final design as described in Section 3.2.4, making it intuitive to pick the best Graph Query that matches researchers' data collection goals.

Our participants identified several novel research opportunities enabled by Crepe's screen data collection capabilities. P1 mentioned the interest in collecting Twitter (X)'s feed data to understand the platform's feed algorithm. P2 would like to collect data from Uber to understand how ride prices change throughout a day and throughout different days of a week. P5 proposed to collect journal apps' suggestion prompts to gauge what the app understands about users' everyday activities. Interestingly, P1 also brought up the need to collect data based on certain conditions: for example, only collect social media feed under the "For you" tab instead of "Following". This can further expand the utility of Crepe.

---

[FIGURE 7]
*Figure 7: The usability questionnaire results for Study 1, evaluating researchers' perception of Crepe's usability and data collection capabilities. The tool received positive feedback, demonstrating its usability and utility for potential data collections studies.*

---

### 4.3 Study 2: Evaluating Graph Query Data Collection Accuracy (In-Lab)

Study 2 evaluates how accurately Crepe collects screen data in realistic app usage scenarios. While Study 1 focused on researchers' experience creating data collectors, this study examines the technical performance of Graph Query in locating and extracting target data.

For mobile screen data collection tasks, it is not easy to establish accurate ground truth, i.e., all of the data we are supposed to collect. Measuring screen data collection accuracy requires us to compare (1) the target data that showed up on users' screens (i.e., the ground truth), and (2) the data the tool is able to collect. It is almost impractical or impossible to establish the ground truth when the data collection happens in the wild, as we need to screen record all user interactions and manually identify target data on screen. To the best of our knowledge, no automated tool is capable of identifying target data with 100% accuracy, especially given Crepe's specificity towards target data. A previous tool that collects all screen data during a period was not able to compare collected screen data against a rigorous ground truth. Instead, they indirectly proved their collected data contained "no notable anomalies" and they generally followed their expected usage patterns. As a result, to accurately evaluate Crepe's data collection accuracy, we conducted it as an in-lab study, so we can record the screen and manually label a ground truth dataset.

#### 4.3.1 Procedure

We provided participants with a development phone with Crepe pre-installed and configured to collect data from apps in the three defined scenarios (Section 4.1). Each participant spent approximately one hour using these apps, allocating around 20 minutes per app. Participants were instructed to use each app naturally as they would in their daily life, while also feeling free to switch between apps when needed to mirror realistic usage patterns. All studies were carried out in person and participants received $15 digital gift cards for each hour they participated.

To establish ground truth for evaluating collection accuracy, we simultaneously recorded the phone screen during the study sessions. An author labeled the screen recordings to identify all instances where target data appeared as the ground truth, and another author separately verified the results. We compared this ground truth data against the data collected by Crepe to compute collection accuracy.

#### 4.3.2 Participants

We recruited 5 participants through social media advertisements and word-of-mouth. This provided approximately 240 minutes of naturalistic app usage data for our accuracy evaluation, generating a diverse set of UI states and interactions across different apps. Participant demographics and their app usage experience are detailed in Appendix A.3.

#### 4.3.3 Results

Across all sessions, we recorded 528 data points across three apps as the benchmark (284 from Instagram, 119 from Uber, and 125 from Chrome). Crepe achieved an overall collection accuracy F1 score of **96.0%** (precision: 96.0%, recall: 95.8%). Breaking down by app, collection accuracy F-1 scores were consistently high: Uber (98.3%), Instagram (94.8%), Chrome (96.0%). The minor variations in accuracy across apps can be attributed to differences in UI update frequencies and layout complexities.

**Edge cases.** In the evaluation, we observed several scenarios where Crepe can make mistakes in data collection. First, some apps have UI layout variations for the same target data, requiring Crepe to set up multiple Graph Queries to collect the same data (as discussed in Section 3.2.7). In our evaluation, Instagram story's ads are sometimes presented above a TextView containing "Sponsored", and sometimes above a Button containing "Sponsored". However, by demonstrating in both of these scenarios, researchers can still use Crepe to robustly handle such data collection tasks. In fact, we demonstrated three different UI layouts to Crepe during our evaluation study for Instagram Stories. Second, complex UI screens containing more than 500 UI elements can pose challenges to Crepe's processing speed, potentially omitting data due to performance bottlenecks. We set a loose threshold to Crepe's processing frequency to avoid repeatedly collecting the same data. In addition, certain techniques used in App development, such as virtualization, might cause Android Accessibility Service to pick up invisible text on screen. This is also observed in a previous study. We discuss some of our future improvement plans to address these challenges in Section 6.

---

**Table 4: The evaluation results for Crepe in the three app scenarios.** Our in-lab study 2 demonstrates that Crepe performs well on the three selected data collection scenarios. We discuss the observed edge cases that Crepe cannot handle well in Section 4.3.3.

| Metric | Overall | Instagram | Uber | Chrome |
|---|---|---|---|---|
| **Recall** | 95.80% (506/528) | 94.7% (269/284) | 96.6% (115/119) | 97.6% (122/125) |
| **Precision** | 96.00% (504/525) | 95.0% (268/282) | 100% (115/115) | 94.5% (121/128) |
| **F1 Score** | 96.0% | 94.8% | 98.3% | 96.0% |

---

In general, the results show that Graph Query can reliably collect screen data across various apps and UI screens. The collected dataset captured diverse scenarios including real-time price updates in Uber, dynamically positioned sponsored content in Instagram, and recommendation feeds in Chrome homepage. These results validate that Graph Query's data collection mechanism is robust enough for real-world deployment while maintaining high accuracy across different apps and scenarios.

### 4.4 Study 3: Evaluating System Impact for Users (Field Study)

Now that we understand Crepe's performance in lab, how well does it work in the wild? In Study 3, we conducted a field study with users who contributes their screen data through Crepe. Study 3 focuses on the real-world performance of Crepe, especially on its device performance and impact on data contributors' regular phone usage experience. We designed Study 3 to evaluate how Crepe performs on different Android devices and OS versions, helping us catch any real-world deployment issues we couldn't spot in the lab. Study 3 was conducted in example scenario 1 (Instagram story ads), since our target metrics will not significantly change when deployed for different apps' data collections.

**Participants.** We recruited seven participants through social media advertisements and word-of-mouth. The participants are regular users of Instagram and Instagram Story. Each participant decided to contribute their data from 24 hours up to 72 hours based on their preferences and time schedule. We aimed at testing Crepe on various Android versions and device platforms, while also evaluating Crepe's performance over short and longer collection durations. Four participants used their own Android devices. Since our main goal is not to collect a dataset that can be directly used in rigorous quantitative analysis but to empirically test our collector system, we also recruited three participants who are interested but do not have an Android device (P2, P3, P6). We provided each of them with an Android phone, with which they were asked to use Instagram during the period of the study, roughly following their regular Instagram usage habits. These three participants also contributed to our study by helping us assess the performance and usability of Crepe across different usage behaviors.

**Study procedure.** The user study followed a three-stage procedure:

1. A 30-minute introductory interview to familiarize participants with the study and set up Crepe on their devices;
2. A testing period lasting between 24 to 72 hours, based on the participants' time schedule and preferences, during which they were encouraged to use Instagram as usual.
3. A 30-minute concluding interview to administer a post-study questionnaire, collect feedback on participants' experiences, and address any questions or concerns.

Throughout the study, we maintained email communications with participants to ensure Crepe functioned normally and conducted troubleshooting sessions when necessary. Each participant was compensated with 25 USD digital gift card for the data they contributed, and 20 USD for each hour of meeting sessions they attended. The participants' participation duration, device information, and Crepe's battery usage result after the study ended are shown in Table 5.

> *The study protocol was reviewed and approved by the Institutional Review Board (IRB) at our institution.*

---

**Table 5: Mobile device usage data for study participants over 24 to 72 hour periods**, including mobile OS, device model, and battery usage percentage. Three of the participants did not have an Android phone and used our provided device, with which they were asked to use Instagram following their regular habits during the study period.

| Participant | Mobile OS | Device | Period | Battery Usage |
|---|---|---|---|---|
| PC1 | Android 14 | Pixel 8 (own) | 72 hours | 1% |
| PC2 | Android 14 | Pixel 6 (provided) | 72 hours | 14% |
| PC3 | Android 14 | Pixel 6 (provided) | 72 hours | 9% |
| PC4 | Android 13, OxygenOS 13.1 | OnePlus 9R (own) | 24 hours | 0.91% |
| PC5 | Android 12, Oxygen OS 12.1 | OnePlus Nord (own) | 24 hours | N/A |
| PC6 | Android 14 | Pixel 6 (provided) | 24 hours | 2% |
| PC7 | Android 9 | Galaxy S10 (own) | 24 hours | 0% |

---

**Study Results.** After initial data analysis, Crepe was able to collect 358 Instagram Story advertisements from all seven participants, with an average of 51 ads per participant (Figure 8, Figure 9). The collected data reveals the number of unique Instagram Story Ads encountered by each participant at regular time intervals throughout their respective data collection periods. The data allow us to observe the frequency and distribution of Instagram Story Ads over time, potentially providing insights into the advertising strategies employed by businesses on the platform. We shared the data we collected from each participant with them individually upon request.

In the post-study questionnaire, which included two 5-scale questions, all participants unanimously reported that they felt **minimal interruption and disturbance** from Crepe while using their everyday apps and **did not notice significant changes** to their devices during the collection study. Here are details regarding these two questions and all participants' response:

- **Q1:** When using my everyday apps, I felt minimal interruption and disturbance from the Crepe app.
  - All participants responded 5 – Strongly agree
- **Q2:** I noticed significant changes to my device during the data collection study.
  - All participants responded 1 – Strongly disagree

Based on the battery usage data collected in the post-study questionnaire, Crepe demonstrated excellent energy efficiency on participants' mobile devices over the 24 to 72 hour study periods. As shown in Table 5, the battery usage of Crepe ranged from 0%, 0.91% to 14%, with most participants reporting usage of 2% or less. This indicates that running Crepe in the background for data collection has minimal impact on the battery life of participants' smartphones, making it a power-efficient tool for mobile data collection studies.

However, we observed a limitation of Crepe during the study: the background process management on Android can terminate Crepe to conserve resources. This is a known issue for similar mobile data collectors. For P1, we suspect the Android operating system terminated Crepe in the background, resulting in data loss at around hour 30. Only after we noticed it and prompted P1 to check the running status of Crepe did the data resumed to be collected. To address this issue, for later participants, we improved Crepe's "heartbeat" mechanism and had the app send a heartbeat signal every 10 minutes. Once we noticed a potential inactive status of Crepe, we sent reminder emails to participants and asked them to open Crepe and check its running status. In future iterations of Crepe, this heartbeat mechanism could be combined with a dashboard to alert researchers when data collection becomes offline, enabling timely interventions to minimize data loss.

---

[FIGURE 8]
*Figure 8: Temporal patterns of Instagram story ads collected in Study 3 using Crepe. This scatter plot displays unique data from participants P1–P3, who chose a 72-hour study period based on their availability. Circle size corresponds to the number of entries collected at each time point (shown by the number within each circle). The distribution reveals how ad exposure varied across participants and throughout the three-day period, with some participants experiencing more consistent ad delivery while others encountered more sporadic patterns. All data was passively collected while participants engaged in their regular smartphone usage. For the rest of the participants, the 24-hour study results is shown in Figure 9.*

---

[FIGURE 9]
*Figure 9: The distribution of Instagram story ads collected in Study 3 using Crepe. This scatter plot represents unique data collected from participants P4-P7, who chose a 24-hour study period based on their availability. Each circle represents a collection event, with size proportional to the number of ads captured (indicated by the number inside each circle). Participants installed Crepe on their mobile phones and continued their normal daily activities while the system collected Instagram story ads in the background.*

---

### 4.5 Summary

Our three-part evaluation of Crepe examined its effectiveness in supporting researchers' data collection needs (RQ1), accuracy in collecting target screen data (RQ2), and real-world performance impact (RQ3). Study 1 demonstrated that researchers could effectively use Crepe's programming by demonstration approach, with all five participants successfully creating accurate data collectors for three different scenarios and rating the system's usability favorably. Study 2 validated Crepe's technical robustness through an in-lab evaluation, achieving high collection accuracy with an overall F1 score of 96.0% across Instagram, Uber, and Chrome applications, though some challenges emerged with complex UI screens containing over 500 elements. Finally, Study 3's field deployment with seven participants showed that Crepe had minimal impact on device performance, with most participants reporting battery usage of 2% or less and unanimously indicating no noticeable interference with their regular phone usage. The system successfully collected 358 Instagram Story advertisements during the field study, though we identified opportunities for improving background process management to prevent occasional data collection interruptions. Together, these results demonstrate that Crepe effectively balances researcher needs, technical accuracy, and user experience in mobile screen data collection, while highlighting specific areas for future enhancement.

---

## 5 Discussion

### 5.1 Collection Support Tools for De-centralized Data Access

Crepe complements existing open-source data collection tools like AWARE and Purple that focus on collecting sensor data, and others like ShiptCalculator that enable workers to share screenshots of their pay history for wage transparency advocacy. Crepe targets the generalized collection of various types of mobile screen data. This contains great potential for more academic researchers to more easily access datasets and uncover more quantitative, analytical insights. Crepe aligns with the growing movement towards a more open and equitable ecosystem in digital economy.

The democratization of screen information access breaks the "data monopoly" that operating systems providers and app developers have long maintained. It shifts the data ownership back to end users, instead of leaving it only concentrated in the hands of tech platforms. By helping users see their own data, we can enable customized features that monitor and understand their behavior, supporting more informed device and app usage. This transparency allows individuals to make better decisions about their digital habits and identify patterns they might want to change.

By providing academic researchers access to screen data, they can better audit algorithms without depending on platform APIs that companies can (and often do) remove at will. This independent access creates a more sustainable research ecosystem that isn't vulnerable to corporate gatekeeping. Researchers can investigate questions about algorithmic bias, content recommendation systems, or user experience issues with greater freedom and thoroughness. This approach represents a fundamental shift in how we think about digital data ownership, treating screen data as something that belongs primarily to users rather than platforms. It encourages a more balanced relationship between tech companies, users, and the research community.

### 5.2 Graph Query for Post-Collection Data Filtering

While Crepe's current design focuses on prospective data collection where researchers define Graph Queries before deployment, a potential alternative approach is to collect comprehensive app-level data first similar to existing tools, then use Graph Query retrospectively to filter relevant information. This provides the benefit of retaining contextual information about the full UI state and enabling researchers to iteratively refine their data collection criteria without redeploying to participants. In this way, researchers could iteratively refine Graph Queries on stored UI snapshots, similar to writing SQL queries to explore structured data without re-collecting, enabling exploratory analysis and hypothesis refinement post-deployment. But at the same time, this retrospective approach would require the initial data collection phase to store UI Snapshot information (including all screen entity relations) rather than only the final extracted values. This comprehensive collection increases storage requirements and privacy concerns but provides flexibility for researchers to discover unexpected patterns or change research questions post-collection, with Graph Query serving as the unified querying mechanism for both use cases.

### 5.3 Careful Considerations for User Privacy

The collection of user data through Crepe raises important privacy concerns regarding users' app usage and screen information. Throughout the design and implementation of Crepe, user privacy has been a top priority, ensuring real-time transparency of collected data and employing high-standard encryption for data security. It is crucial to emphasize that Crepe is intended solely for research purposes, under scenarios where researchers obtain explicit consent from participants to collect screen data. In the future, we plan to continuously enhance the privacy-related features in Crepe. For instance, prior to the public release of Crepe, we intend to include a feature that hashes personal identifiers before sending them to researchers, thereby protecting users' privacy, similar to the approach taken by previous data collectors. There have also been differential-privacy-based approaches that obfuscate sensitive data on collected mobile app UI snapshots, which we can adopt in Crepe. We acknowledge that protecting users' privacy in data collection remains an open research question, and we encourage the research community to collectively work towards improving our ethical standards in this regard.

### 5.4 Implications for Data Labor and Data Governance

Our approach for the decentralization of data access has important implications for data governance and the broader ecosystem of data-driven technologies. The rise of digital platforms has led to the concentration of user data in the hands of corporations and platforms, creating a "data monopoly" that limits the potential benefits of academic research and user-centric data-driven technologies. By breaking the data monopoly and providing users with access to their own data, our approach can help bridge the data divide and empowers individuals and communities to leverage their own data for personal and collective benefits, rather than being solely exploited by corporations.

This increased transparency can help to identify and address biases and inequalities in the algorithms. By providing access to users' own data on platforms, distributed, user-centric data-driven technologies can be developed in user groups and communities to shift the focus of benefits from corporations and platforms to end users. This aligns with the vision of a more equitable data ecosystem, where the value generated by user data is distributed more fairly among stakeholders.

---

## 6 Limitations and Future Work

While Crepe offers a novel approach to mobile screen data collection, we acknowledge several limitations and opportunities for future enhancement.

### 6.1 Evaluation Study Scale

Our evaluation consists of three segmented studies, each designed to assess specific aspects of Crepe with practical constraints inherent to each study type. While these studies validate core functionality and usability, they involve smaller participant pools and controlled scenarios. Our Study 2 was also limited by the fact that it was conducted using one device type. We acknowledge that real-world deployment at scale may surface challenges not captured in our controlled evaluation. To address this, we plan to conduct a larger-scale real-world deployment to evaluate Crepe's robustness in naturalistic settings. By open-sourcing Crepe, we will work with the research community to iteratively identify and resolve issues across diverse use cases.

### 6.2 Practical Deployment Constraints

Crepe can be terminated by the system after periods of inactivity, potentially leading to data loss—a known issue for mobile data collectors. We implemented a heartbeat mechanism to partially address this and plan to refine Crepe's notification system for scenarios where background processes are killed. Additionally, system or app updates can change UI hierarchies, invalidating pre-defined Graph Queries and requiring researchers to update them. We proposed workarounds for similar situations in Table 3. Multi-cultural data collection remains challenging for apps with localization variations (e.g., RTL/LTR layouts) or diverse screen sizes. However, Graph Query provides an extensible foundation to address these issues—for example, using virtual device emulators to generate multiple queries tailored to different locales and configurations.

### 6.3 Data Collection Accuracy and Media Type

Ensuring data collection accuracy without ground truth is challenging, as discussed in Section 4.3. Researchers must manually test Graph Queries across multiple screens to verify consistent results. Future work could incorporate end-to-end testing frameworks to automatically validate queries before deployment. Additionally, Android Accessibility Service occasionally captures invisible UI elements, introducing noise that could be mitigated by triangulating with OCR results. Meanwhile, Crepe's current focus is on textual data, with potential for richer multimodal data such as screenshots and user interactions. Information rendered in game or 3D engines cannot be collected, as they do not appear in Accessibility Service responses. We plan to integrate additional media types supported by Android Accessibility Service, such as images and screenshots.

### 6.4 Future Enhancements

Taking inspiration from PBD studies, future work could ask users to demonstrate multiple target data examples. Developing visualization dashboards would enable real-time monitoring for researchers and participants. Empowering users to delete collected data after dropout would enhance agency. We plan to open source Crepe to promote ethical use in academic research and welcome community contributions to make it more robust and adaptive to diverse data collection scenarios.

---

## 7 Conclusion

In this paper, we introduce Crepe, a novel mobile data collection tool that enables researchers to easily define and collect user interface screen data from participants' Android devices. Crepe utilizes Graph Query, which allows flexible identification, location, and extraction of target UI elements. The tool's key feature is its low-code, programming by demonstration approach that lets researchers specify data to collect through simple interactions with example app screens. A user study with 7 participants demonstrated Crepe's ability to effectively collect screen UI data across different devices, while identifying areas for future improvements. Overall, Crepe represents an important step towards democratizing mobile app data for research by reducing technical barriers and giving participants more agency. Code for Crepe will be open-sourced to support the academic community in future research data collection.

## Acknowledgments

We extend our sincere appreciation to our participants for their contributions to this project. We thank all anonymous reviewers for their feedback. This work is supported in part by the U.S. National Science Foundation under grants CMMI-2326378 and CNS-2426395, a Google Research Scholar Award, and a gift from Adobe Inc. Any opinions, findings, and conclusions or recommendations expressed in this material are those of the authors and do not necessarily reflect the views of the sponsors.

---

## References

1. Nadav Aharony, Wei Pan, Cory Ip, Inas Khayal, and Alex Pentland. 2011. The social fMRI: measuring, understanding, and designing social mechanisms in the real world. In *Proceedings of the 13th international conference on Ubiquitous computing*. ACM, Beijing China, 445–454. doi:10.1145/2030112.2030171

2. V Aho Alfred, S Lam Monica, and D Ullman Jeffrey. 2007. *Compilers principles, techniques & tools*. Pearson Education.

3. Android Developers. 2025. AccessibilityService: takeScreenshot() method. https://developer.android.com/reference/android/accessibilityservice/AccessibilityService#takeScreenshot

4. Android Developers. 2025. Android API reference: AccessibilityNodeInfo. Google. https://developer.android.com/reference/android/view/accessibility/AccessibilityNodeInfo

5. Imanol Arrieta-Ibarra, Leonard Goff, Diego Jiménez-Hernández, Jaron Lanier, and E. Glen Weyl. 2018. Should We Treat Data as Labor? Moving beyond "Free". *AEA Papers and Proceedings* 108 (2018), 38–42.

6. Delia Cristina Balaban, Meda Mucundorfeanu, and Larisa Ioana Mureșan. 2022. Adolescents' Understanding of the Model of Sponsored Content of Social Media Influencer Instagram Stories. *Media and Communication* 10, 1 (March 2022), 305–316. doi:10.17645/mac.v10i1.4652

7. Barbara Ballard. 2007. *Designing the mobile user experience*. John Wiley & Sons.

8. Jenae Barnes. 2023. Twitter Ends Its Free API: Here's Who Will Be Affected. https://www.forbes.com/sites/jenaebarnes/2023/02/03/twitter-ends-its-free-api-heres-who-will-be-affected/

9. Frank R Bentley, S Tejaswi Peesapati, and Karen Church. 2016. "I thought she would like to read it" Exploring Sharing Behaviors in the Context of Declining Mobile Web Use. In *Proceedings of the 2016 CHI Conference on Human Factors in Computing Systems*. 1893–1903.

10. John Brooke. 1996. SUS: A "quick and dirty" usability scale. In *Usability Evaluation in Industry*. Taylor & Francis, London, 189–194.

11. Barry Brown, Moira McGregor, and Eric Laurier. 2013. iPhone in vivo: video analysis of mobile device use. In *Proceedings of the SIGCHI conference on Human Factors in computing systems*. 1031–1040.

12. Dan Calacci and Alex Pentland. 2022. Bargaining with the Black-Box: Designing and Deploying Worker-Centric Tools to Audit Algorithmic Management. *Proceedings of the ACM on Human-Computer Interaction* 6, CSCW2 (Nov. 2022), 1–24. doi:10.1145/3570601

13. Giuseppe Cardone, Andrea Cirri, Antonio Corradi, Luca Foschini, and Dario Maio. 2013. MSF: An Efficient Mobile Phone Sensing Framework. *International Journal of Distributed Sensor Networks* 9, 3 (March 2013), 538937.

14. Vageesh Chandramouli, Abhijnan Chakraborty, Vishnu Navda, Saikat Guha, Venkata Padmanabhan, and Ramachandran Ramjee. 2015. Insider: Towards breaking down mobile app silos. In *TRIOS Workshop held in conjunction with the SIGOPS SOSP*. Citeseer.

15. Junzhi Chao. 2019. Modeling and analysis of uber's rider pricing. In *2019 International Conference on Economic Management and Cultural Industry (ICEMCI 2019)*. Atlantis Press, 693–711.

16. Chaoran Chen, Weijun Li, Wenxin Song, Yanfang Ye, Yaxing Yao, and Toby Jia-jun Li. 2024. An Empathy-Based Sandbox Approach to Bridge the Privacy Gap among Attitudes, Goals, Knowledge, and Behaviors. doi:10.1145/3613904.3642363

17. James Clark, Steve DeRose, et al. 1999. XML path language (XPath).

18. Composables. 2025. Android Distribution Chart. https://composables.com/android-distribution-chart

19. Allen Cypher. 1991. Eager: Programming repetitive tasks by example. In *Proceedings of the SIGCHI conference on Human factors in computing systems*. 33–39.

20. Allen Cypher and Daniel Conrad Halbert. 1993. *Watch what I do: programming by demonstration*. MIT press.

21. Allen Cypher and Daniel Conrad Halbert. 1993. *Watch what I Do: Programming by Demonstration*. MIT Press.

22. Shaunak De, Abhishek Maity, Vritti Goel, Sanjay Shitole, and Avik Bhattacharya. 2017. Predicting the Popularity of Instagram Posts for a Lifestyle Magazine Using Deep Learning. doi:10.1109/CSCITA.2017.8066548

23. Biplab Deka, Zifeng Huang, Chad Franzen, Joshua Hibschman, Daniel Afergan, Yang Li, Jeffrey Nichols, and Ranjitha Kumar. 2017. Rico: A Mobile App Dataset for Building Data-Driven Design Applications. In *Proceedings of the 30th Annual ACM Symposium on User Interface Software and Technology*. 845–854.

24. Motahhare Eslami, Karrie Karahalios, Christian Sandvig, Kristen Vaccaro, Aimee Rickman, Kevin Hamilton, and Alex Kirlik. 2016. First I "like" it, then I hide it: Folk Theories of Social Feeds. In *Proceedings of the 2016 CHI Conference on Human Factors in Computing Systems*. 2371–2382.

25. Motahhare Eslami, Aimee Rickman, Kristen Vaccaro, Amirhossein Aleyasen, Andy Vuong, Karrie Karahalios, Kevin Hamilton, and Christian Sandvig. 2015. "I always assumed that I wasn't really that close to [her]": Reasoning about Invisible Algorithms in News Feeds. In *Proceedings of the 33rd Annual ACM Conference on Human Factors in Computing Systems*. 153–162.

26. Dovan Fakhradyan. 2021. The Study of Consumer Preferences and Advertising Effectiveness Analysis Towards Studio Hikari Instagram Story Video Ads. *Jurnal Ilmu Sosial Politik dan Humaniora* 4, 1 (March 2021), 10–18.

27. Denzil Ferreira, Vassilis Kostakos, and Anind K. Dey. 2015. AWARE: Mobile Context Instrumentation Framework. *Frontiers in ICT* 2 (2015).

28. Andrea Generosi, Silvia Ceccacci, Samuele Faggiano, Luca Giraldi, and Maura Mengoni. 2020. A Toolkit for the Automatic Analysis of Human Behavior in HCI Applications in the Wild. *Advances in Science, Technology and Engineering Systems Journal* 5, 6 (2020), 185–192.

29. Andrew M Guess, Neil Malhotra, Jennifer Pan, Pablo Barberá, Hunt Allcott, Taylor Brown, Adriana Crespo-Tenorio, Drew Dimmery, Deen Freelon, Matthew Gentzkow, et al. 2023. How do social media feed algorithms affect attitudes and behavior in an election campaign? *Science* 381, 6656 (2023), 398–404.

30. René Haldborg Jørgensen, Hilde A.M Voorveld, and Guda van Noort. 2023. Instagram Stories: How Ephemerality Affects Consumers' Responses Toward Instagram Content and Advertising. *Journal of Interactive Advertising* 23, 3 (July 2023), 187–202.

31. Alaa Hanbazazh and Carlton Reeve. 2021. Pop-up Ads and Behaviour Patterns: A Quantitative Analysis Involving Perception of Saudi Users. *International Journal of Marketing Studies* 13, 4 (Nov. 2021), 31.

32. Joel M. Hektner, Jennifer Anne Schmidt, and Mihaly Csikszentmihalyi. 2007. *Experience Sampling Method: Measuring the Quality of Everyday Life*. SAGE.

33. Toby Jia-Jun Li, Yuwen Lu, Jaylexia Clark, Meng Chen, Victor Cox, Meng Jiang, Yang Yang, Tamara Kay, Danielle Wood, and Jay Brockman. 2022. A Bottom-Up End-User Intelligent Assistant Approach to Empower Gig Workers against AI Inequality. doi:10.48550/arXiv.2204.13842

34. Levi Kaplan and Piotr Sapiezynski. 2024. Comprehensively Auditing the TikTok Mobile App. In *Companion Proceedings of the ACM on Web Conference 2024*. 1198–1201.

35. Ian Kim, Jack Boffa, Mujung Cho, David E Conroy, Nathan Kline, Nick Haber, Thomas N Robinson, Byron Reeves, and Nilam Ram. 2025. Stanford Screenomics: An Open-source Platform for Unobtrusive Multimodal Digital Trace Data Collection from Android Smartphones. *medRxiv* (2025), 2025–06.

36. Nima Kordzadeh and Maryam Ghasemaghaei. 2022. Algorithmic bias: review, synthesis, and future research directions. *European Journal of Information Systems* 31, 3 (May 2022), 388–409.

37. Adam D. I. Kramer, Jamie E. Guillory, and Jeffrey T. Hancock. 2014. Experimental evidence of massive-scale emotional contagion through social networks. *Proceedings of the National Academy of Sciences* 111, 24 (June 2014), 8788–8790.

38. Philipp Krieter. 2019. Can I record your screen? mobile screen recordings as a long-term data source for user studies. In *Proceedings of the 18th International Conference on Mobile and Ubiquitous Multimedia (MUM '19)*. 1–10.

39. Anita S Lenjo. 2017. *A qualitative study on the lived experiences of young entrepreneurs participating in the futuristic UBER business model*. Ph.D. Dissertation. University of Nairobi.

40. Toby Jia-Jun Li, Amos Azaria, and Brad A. Myers. 2017. SUGILITE: Creating Multimodal Smartphone Automation by Demonstration. In *Proceedings of the 2017 CHI Conference on Human Factors in Computing Systems*. 6038–6049.

41. Toby Jia-Jun Li, Jingya Chen, Brandon Canfield, and Brad A Myers. 2020. Privacy-preserving script sharing in gui-based programming-by-demonstration systems. *Proceedings of the ACM on Human-Computer Interaction* 4, CSCW1 (2020), 1–23.

42. Toby Jia-Jun Li, Igor Labutov, Xiaohan Nancy Li, Xiaoyi Zhang, Wenze Shi, Wanling Ding, Tom M Mitchell, and Brad A Myers. 2018. Appinite: A multi-modal interface for specifying data descriptions in programming by demonstration using natural language instructions. In *2018 IEEE Symposium on Visual Languages and Human-Centric Computing (VL/HCC)*. IEEE, 105–114.

43. Toby Jia-Jun Li, Lindsay Popowski, Tom Mitchell, and Brad A Myers. 2021. Screen2Vec: Semantic Embedding of GUI Screens and GUI Components. In *Proceedings of the 2021 CHI Conference on Human Factors in Computing Systems*. 1–15.

44. Henry Lieberman et al. 2000. *Your wish is my command*. San Francisco: Morgan Kaufrnann.

45. Trishan Panch, Heather Mattie, and Rifat Atun. 2021. Artificial intelligence and algorithmic bias: implications for health systems. *Journal of Global Health* 9, 2 (June 2021), 020318.

46. Eric A. Posner and E. Glen Weyl. 2018. *Radical Markets: Uprooting Capitalism and Democracy for a Just Society*. Princeton University Press.

47. Mika Raento, Antti Oulasvirta, and Nathan Eagle. 2009. Smartphones: An emerging tool for social scientists. *Sociological Methods & Research* 37, 3 (2009), 426–454.

48. Staff Reddit. 2023. Key Facts to Understanding Reddit's Recent API Updates - Upvoted. https://www.redditinc.com/blog/apifacts

49. Manoel Horta Ribeiro, Raphael Ottoni, Robert West, Virgílio AF Almeida, and Wagner Meira Jr. 2020. Auditing radicalization pathways on YouTube. In *Proceedings of the 2020 conference on fairness, accountability, and transparency*. 131–141.

50. Thomas N. Robinson, Jorge A. Banda, Lauren Hale, Amy Shirong Lu, Frances Fleming-Milici, Sandra L. Calvert, and Ellen Wartella. 2017. Screen Media Exposure and Obesity in Children and Adolescents. *Pediatrics* 140, Supplement_2 (Nov. 2017), S97–S101.

51. Yvonne Rogers and Paul Marshall. 2017. *Research in the Wild*. Morgan & Claypool Publishers.

52. Christian Sandvig, Kevin Hamilton, Karrie Karahalios, and Cedric Langbort. 2014. Auditing algorithms: Research methods for detecting discrimination on internet platforms. *Data and discrimination: converting critical concerns into productive inquiry* 22, 2014 (2014), 4349–4357.

53. Stephen M. Schueller, Mark Begale, Frank J. Penedo, and David C. Mohr. 2014. Purple: A Modular System for Developing and Deploying Behavioral Intervention Technologies. *Journal of Medical Internet Research* 16, 7 (July 2014), e3376.

54. Kate Starbird, Jim Maddock, Mania Orand, Peg Achterman, and Robert M. Mason. 2014. Rumors, False Flags, and Digital Vigilantes: Misinformation on Twitter after the 2013 Boston Marathon Bombing. *iConference 2014 Proceedings* (March 2014).

55. Kate Starbird and Leysia Palen. 2010. Pass It On?: Retweeting in Mass Emergency. *Pass It On* (2010).

56. Songyan Teng, Simon D'Alfonso, and Vassilis Kostakos. 2024. A tool for capturing smartphone screen text. In *Proceedings of the 2024 CHI Conference on Human Factors in Computing Systems*. 1–24.

57. Lena Ulbricht and Karen Yeung. 2022. Algorithmic regulation: A maturing concept for investigating regulation of and through algorithms. *Regulation & Governance* 16, 1 (2022), 3–22.

58. Niels van Berkel, Denzil Ferreira, and Vassilis Kostakos. 2017. The Experience Sampling Method on Mobile Devices. *Comput. Surveys* 50, 6 (Dec. 2017), 93:1–93:40.

59. Sarah Vieweg, Amanda L. Hughes, Kate Starbird, and Leysia Palen. 2010. Microblogging during two natural hazards events: what twitter may contribute to situational awareness. In *Proceedings of the SIGCHI Conference on Human Factors in Computing Systems*. 1079–1088.

60. Bryan Wang, Gang Li, and Yang Li. 2023. Enabling Conversational Interaction with Mobile UI using Large Language Models. doi:10.48550/arXiv.2209.08655

61. Bryan Wang, Gang Li, Xin Zhou, Zhourong Chen, Tovi Grossman, and Yang Li. 2021. Screen2Words: Automatic Mobile UI Summarization with Multimodal Learning. doi:10.48550/arXiv.2108.03353

62. An Yan, Zhengyuan Yang, Wanrong Zhu, Kevin Lin, Linjie Li, Jianfeng Wang, Jianwei Yang, Yiwu Zhong, Julian McAuley, Jianfeng Gao, Zicheng Liu, and Lijuan Wang. 2023. GPT-4V in Wonderland: Large Multimodal Models for Zero-Shot Smartphone GUI Navigation. doi:10.48550/arXiv.2311.07562

63. Zhen Yue, Eden Litt, Carrie J. Cai, Jeff Stern, Kathy K. Baxter, Zhiwei Guan, Nikhil Sharma, and Guangqiang (George) Zhang. 2014. Photographing information needs: the role of photos in experience sampling method-style research. In *Proceedings of the SIGCHI Conference on Human Factors in Computing Systems*. 1545–1554.

64. Guanjie Zheng, Fuzheng Zhang, Zihan Zheng, Yang Xiang, Nicholas Jing Yuan, Xing Xie, and Zhenhui Li. 2018. DRN: A deep reinforcement learning framework for news recommendation. In *Proceedings of the 2018 world wide web conference*. 167–176.

---

## A Appendix

### A.1 Details of Our Graph Query Translation Prompt

As described in Section 3.2.2, we used large language models to translate the candidate graph queries to natural language. Specifically, our prompt uses the following structure:

> We defined a Graph Query to locate target data on mobile UI structure. It describes the unique attributes of the data we are targeting. For example, the query
>
> ```
> (conj (HAS_CLASS_NAME android.widget.FrameLayout)
>  (RIGHT (conj (hasText 6) (HAS_CLASS_NAME android.widget.TextView)
>   (HAS_PACKAGE_NAME com.ubercab))) (HAS_PACKAGE_NAME com.ubercab))
> ```
>
> stands for: the information that is located to the right of a text "6"
>
> Below I have a few queries, can you help me translate them to human-readable format like above?
>
> 1. ... (first query)
> 2. ... (second query)
> 3. ... (etc.)
>
> Leave out UI element names (TextView, FrameLayout) and do not make any reference to "view". Users only care about the data and information contained in the view instead of the UI elements themselves. "With numeric index xx" should be translated into "the xx in the list" (first, second, etc.). Be as concise as possible. Make sure you return the translation in the order I presented the queries above, separated by new lines. Return nothing else.

### A.2 Evaluation Study 1 Participant Demographics

**Table 6: Demographics of evaluation Study 1 participants** (Section 4.2).

| ID | Age | Gender | Research Experience | Collected Data Types | Data Collection Tools | Data Collection Projects |
|---|---|---|---|---|---|---|
| P1 | 23 | Male | 3 years | IDE logs, eye tracking, semi-structured interview, survey | IDE plugin, screen recorder, audio recorder, eye tracker | 2 |
| P2 | 30 | Female | 5 years | App usage, surveys, interviews | Google Analytics, Amazon Web Services, think-aloud, interviews, surveys, Qualtrics, MAXQDA | About 6 (5–10) |
| P3 | 26 | Male | 4 years | UI interaction, think-aloud, interview | Computer program, recorder | 4 |
| P4 | 32 | Female | 2 years | Interviews | Audio recording | 2 |
| P5 | 26 | Female | 3.5 years | Gaze, image description | Eye tracker | 2 |

### A.3 Evaluation Study 2 Participant Demographics

**Table 7: Demographics information and app usage frequency for evaluation Study 2 participants** (Section 4.3).

| ID | Age | Gender | Instagram Frequency | Uber Frequency | Chrome Mobile Frequency |
|---|---|---|---|---|---|
| PB1 | 21 | Male | Every week | Once in a few weeks | Everyday |
| PB2 | 25 | Male | Everyday | Once in a few months | Everyday |
| PB3 | 23 | Male | Every week | Every week | Everyday |
| PB4 | 30 | Male | Everyday | Once in a few weeks | Everyday |
| PB5 | 26 | Female | Everyday | Once in a few weeks | Everyday |
